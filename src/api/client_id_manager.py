"""Client ID Manager for rotating SoundCloud client IDs."""

import asyncio
import time
from typing import List, Optional, Dict, Any
from enum import Enum

from ..utils.logger import setup_logger


class ClientIDStatus(Enum):
    """Status of a client ID."""
    ACTIVE = "active"
    FAILED = "failed"
    COOLDOWN = "cooldown"


class ClientIDInfo:
    """Information about a single client ID."""
    
    def __init__(self, client_id: str):
        """
        Initialize client ID info.
        
        Args:
            client_id: The SoundCloud client ID
        """
        self.client_id = client_id
        self.status = ClientIDStatus.ACTIVE
        self.fail_count = 0
        self.last_failed_at: Optional[float] = None
        self.last_used_at: Optional[float] = None
        self.success_count = 0
        self.created_at = time.time()
    
    def mark_success(self) -> None:
        """Mark this client ID as successfully used."""
        self.success_count += 1
        self.last_used_at = time.time()
        if self.status == ClientIDStatus.COOLDOWN:
            # ID recovered, reset to active
            self.status = ClientIDStatus.ACTIVE
            self.fail_count = 0
    
    def mark_failed(self, error_code: int) -> None:
        """
        Mark this client ID as failed.
        
        Args:
            error_code: HTTP error code (401, 403, etc.)
        """
        self.fail_count += 1
        self.last_failed_at = time.time()
        
        # 401/403 means the ID is invalid
        if error_code in (401, 403):
            self.status = ClientIDStatus.FAILED
        else:
            # Other errors - put in cooldown
            self.status = ClientIDStatus.COOLDOWN
    
    def can_retry(self, cooldown_seconds: int = 300) -> bool:
        """
        Check if this ID can be retried after cooldown.
        
        Args:
            cooldown_seconds: Cooldown period in seconds
            
        Returns:
            True if ID can be retried
        """
        if self.status == ClientIDStatus.ACTIVE:
            return True
        
        if self.status == ClientIDStatus.FAILED:
            # Failed IDs can be retried after longer cooldown (for health check)
            if self.last_failed_at:
                return (time.time() - self.last_failed_at) > (cooldown_seconds * 6)
            return False
        
        if self.status == ClientIDStatus.COOLDOWN:
            if self.last_failed_at:
                return (time.time() - self.last_failed_at) > cooldown_seconds
            return True
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/monitoring."""
        return {
            'client_id': self.client_id[:8] + '...',  # Truncate for security
            'status': self.status.value,
            'fail_count': self.fail_count,
            'success_count': self.success_count,
            'last_failed_at': self.last_failed_at,
            'last_used_at': self.last_used_at,
        }


class ClientIDManager:
    """Manager for rotating and managing multiple SoundCloud client IDs."""
    
    def __init__(
        self,
        client_ids: List[str],
        strategy: str = 'failover',
        cooldown_seconds: int = 300
    ):
        """
        Initialize Client ID Manager.
        
        Args:
            client_ids: List of SoundCloud client IDs
            strategy: Rotation strategy ('failover' or 'round-robin')
            cooldown_seconds: Cooldown period for failed IDs
        """
        if not client_ids:
            raise ValueError("At least one client ID is required")
        
        self.logger = setup_logger()
        self.strategy = strategy
        self.cooldown_seconds = cooldown_seconds
        
        # Initialize client ID info objects
        self.client_ids: List[ClientIDInfo] = [
            ClientIDInfo(cid.strip()) for cid in client_ids if cid.strip()
        ]
        
        if not self.client_ids:
            raise ValueError("No valid client IDs provided")
        
        self.current_index = 0
        self._lock = asyncio.Lock()
        
        self.logger.info(
            f"ClientIDManager initialized with {len(self.client_ids)} client IDs, "
            f"strategy: {strategy}"
        )
    
    async def get_active_id(self) -> str:
        """
        Get an active client ID based on the rotation strategy.
        
        Returns:
            Active client ID string
            
        Raises:
            RuntimeError: If no active client IDs available
        """
        async with self._lock:
            if self.strategy == 'failover':
                return await self._get_failover_id()
            elif self.strategy == 'round-robin':
                return await self._get_round_robin_id()
            else:
                return await self._get_failover_id()
    
    async def _get_failover_id(self) -> str:
        """
        Get client ID using failover strategy.
        Uses current ID until it fails, then switches to next.
        
        Returns:
            Client ID string
            
        Raises:
            RuntimeError: If no active IDs available
        """
        # Try current index first
        current = self.client_ids[self.current_index]
        if current.status == ClientIDStatus.ACTIVE:
            return current.client_id
        
        # Try to find next active ID
        for i in range(len(self.client_ids)):
            idx = (self.current_index + i) % len(self.client_ids)
            candidate = self.client_ids[idx]
            
            if candidate.status == ClientIDStatus.ACTIVE:
                self.current_index = idx
                self.logger.info(
                    f"Switched to client_id #{idx + 1} "
                    f"({candidate.client_id[:8]}...)"
                )
                return candidate.client_id
            
            # Try IDs in cooldown that are ready for retry
            if candidate.can_retry(self.cooldown_seconds):
                self.current_index = idx
                self.logger.info(
                    f"Retrying client_id #{idx + 1} after cooldown "
                    f"({candidate.client_id[:8]}...)"
                )
                candidate.status = ClientIDStatus.ACTIVE
                return candidate.client_id
        
        # No active IDs found
        self.logger.error("All client IDs are exhausted!")
        raise RuntimeError(
            "No active client IDs available. "
            "Please add new client IDs or wait for cooldown period."
        )
    
    async def _get_round_robin_id(self) -> str:
        """
        Get client ID using round-robin strategy.
        Distributes requests evenly across all active IDs.
        
        Returns:
            Client ID string
            
        Raises:
            RuntimeError: If no active IDs available
        """
        # Try to find next active ID in round-robin fashion
        start_idx = self.current_index
        
        for attempt in range(len(self.client_ids)):
            idx = (start_idx + attempt) % len(self.client_ids)
            candidate = self.client_ids[idx]
            
            if candidate.status == ClientIDStatus.ACTIVE:
                self.current_index = (idx + 1) % len(self.client_ids)
                return candidate.client_id
            
            # Try IDs in cooldown
            if candidate.can_retry(self.cooldown_seconds):
                self.current_index = (idx + 1) % len(self.client_ids)
                candidate.status = ClientIDStatus.ACTIVE
                return candidate.client_id
        
        # No active IDs found
        raise RuntimeError(
            "No active client IDs available. "
            "Please add new client IDs or wait for cooldown period."
        )
    
    async def mark_success(self, client_id: str) -> None:
        """
        Mark a client ID as successfully used.
        
        Args:
            client_id: The client ID that was used successfully
        """
        async with self._lock:
            for info in self.client_ids:
                if info.client_id == client_id:
                    info.mark_success()
                    self.logger.debug(
                        f"Client ID {client_id[:8]}... marked as successful "
                        f"(total: {info.success_count})"
                    )
                    break
    
    async def mark_failed(self, client_id: str, error_code: int = 401) -> None:
        """
        Mark a client ID as failed.
        
        Args:
            client_id: The client ID that failed
            error_code: HTTP error code
        """
        async with self._lock:
            for info in self.client_ids:
                if info.client_id == client_id:
                    info.mark_failed(error_code)
                    self.logger.warning(
                        f"Client ID {client_id[:8]}... marked as failed "
                        f"(code: {error_code}, status: {info.status.value}, "
                        f"fail_count: {info.fail_count})"
                    )
                    break
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all client IDs.
        
        Returns:
            Dictionary with statistics
        """
        stats = {
            'total': len(self.client_ids),
            'active': sum(1 for info in self.client_ids if info.status == ClientIDStatus.ACTIVE),
            'failed': sum(1 for info in self.client_ids if info.status == ClientIDStatus.FAILED),
            'cooldown': sum(1 for info in self.client_ids if info.status == ClientIDStatus.COOLDOWN),
            'strategy': self.strategy,
            'current_index': self.current_index,
            'client_ids': [info.to_dict() for info in self.client_ids]
        }
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all client IDs.
        
        Returns:
            Health check results
        """
        self.logger.info("Performing health check on all client IDs...")
        
        stats = self.get_stats()
        
        self.logger.info(
            f"Health check results: {stats['active']} active, "
            f"{stats['failed']} failed, {stats['cooldown']} in cooldown"
        )
        
        return stats
