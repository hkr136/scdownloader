"""Tests for ClientIDManager."""

import pytest
import asyncio
from unittest.mock import Mock, patch
from src.api.client_id_manager import (
    ClientIDManager,
    ClientIDInfo,
    ClientIDStatus
)


class TestClientIDInfo:
    """Tests for ClientIDInfo class."""
    
    def test_init(self):
        """Test initialization."""
        info = ClientIDInfo("test_id_123")
        assert info.client_id == "test_id_123"
        assert info.status == ClientIDStatus.ACTIVE
        assert info.fail_count == 0
        assert info.success_count == 0
    
    def test_mark_success(self):
        """Test marking ID as successful."""
        info = ClientIDInfo("test_id")
        info.mark_success()
        assert info.success_count == 1
        assert info.last_used_at is not None
    
    def test_mark_failed_auth_error(self):
        """Test marking ID as failed with auth error."""
        info = ClientIDInfo("test_id")
        info.mark_failed(401)
        assert info.fail_count == 1
        assert info.status == ClientIDStatus.FAILED
        assert info.last_failed_at is not None
    
    def test_mark_failed_other_error(self):
        """Test marking ID as failed with non-auth error."""
        info = ClientIDInfo("test_id")
        info.mark_failed(500)
        assert info.fail_count == 1
        assert info.status == ClientIDStatus.COOLDOWN
    
    def test_recovery_from_cooldown(self):
        """Test recovery from cooldown status."""
        info = ClientIDInfo("test_id")
        info.mark_failed(500)
        assert info.status == ClientIDStatus.COOLDOWN
        
        info.mark_success()
        assert info.status == ClientIDStatus.ACTIVE
        assert info.fail_count == 0


class TestClientIDManager:
    """Tests for ClientIDManager class."""
    
    def test_init_single_id(self):
        """Test initialization with single ID."""
        manager = ClientIDManager(["id1"])
        assert len(manager.client_ids) == 1
        assert manager.client_ids[0].client_id == "id1"
    
    def test_init_multiple_ids(self):
        """Test initialization with multiple IDs."""
        manager = ClientIDManager(["id1", "id2", "id3"])
        assert len(manager.client_ids) == 3
    
    def test_init_empty_list(self):
        """Test initialization with empty list raises error."""
        with pytest.raises(ValueError, match="At least one client ID is required"):
            ClientIDManager([])
    
    def test_init_whitespace_ids(self):
        """Test initialization filters out whitespace-only IDs."""
        manager = ClientIDManager(["id1", "  ", "id2", ""])
        assert len(manager.client_ids) == 2
    
    @pytest.mark.asyncio
    async def test_get_active_id_failover(self):
        """Test getting active ID with failover strategy."""
        manager = ClientIDManager(["id1", "id2", "id3"], strategy='failover')
        
        # Should return first ID
        id1 = await manager.get_active_id()
        assert id1 == "id1"
        
        # Should still return first ID
        id2 = await manager.get_active_id()
        assert id2 == "id1"
    
    @pytest.mark.asyncio
    async def test_get_active_id_round_robin(self):
        """Test getting active ID with round-robin strategy."""
        manager = ClientIDManager(["id1", "id2", "id3"], strategy='round-robin')
        
        # Should rotate through IDs
        id1 = await manager.get_active_id()
        assert id1 == "id1"
        
        id2 = await manager.get_active_id()
        assert id2 == "id2"
        
        id3 = await manager.get_active_id()
        assert id3 == "id3"
        
        # Should wrap around
        id4 = await manager.get_active_id()
        assert id4 == "id1"
    
    @pytest.mark.asyncio
    async def test_failover_on_failure(self):
        """Test failover when ID fails."""
        manager = ClientIDManager(["id1", "id2", "id3"], strategy='failover')
        
        # Get first ID
        id1 = await manager.get_active_id()
        assert id1 == "id1"
        
        # Mark it as failed
        await manager.mark_failed("id1", 401)
        
        # Should switch to next ID
        id2 = await manager.get_active_id()
        assert id2 == "id2"
        
        # Should keep using second ID
        id3 = await manager.get_active_id()
        assert id3 == "id2"
    
    @pytest.mark.asyncio
    async def test_all_ids_failed(self):
        """Test behavior when all IDs are failed."""
        manager = ClientIDManager(["id1", "id2"], strategy='failover')
        
        # Fail both IDs
        await manager.mark_failed("id1", 401)
        await manager.mark_failed("id2", 403)
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="No active client IDs available"):
            await manager.get_active_id()
    
    @pytest.mark.asyncio
    async def test_mark_success(self):
        """Test marking ID as successful."""
        manager = ClientIDManager(["id1", "id2"])
        
        await manager.mark_success("id1")
        
        # Check the ID was marked successful
        assert manager.client_ids[0].success_count == 1
    
    @pytest.mark.asyncio
    async def test_mark_failed(self):
        """Test marking ID as failed."""
        manager = ClientIDManager(["id1", "id2"])
        
        await manager.mark_failed("id1", 401)
        
        # Check the ID was marked failed
        assert manager.client_ids[0].status == ClientIDStatus.FAILED
        assert manager.client_ids[0].fail_count == 1
    
    def test_get_stats(self):
        """Test getting statistics."""
        manager = ClientIDManager(["id1", "id2", "id3"])
        
        stats = manager.get_stats()
        
        assert stats['total'] == 3
        assert stats['active'] == 3
        assert stats['failed'] == 0
        assert stats['cooldown'] == 0
        assert stats['strategy'] == 'failover'
        assert len(stats['client_ids']) == 3
    
    @pytest.mark.asyncio
    async def test_get_stats_with_failures(self):
        """Test statistics with some failed IDs."""
        manager = ClientIDManager(["id1", "id2", "id3"])
        
        await manager.mark_failed("id1", 401)
        await manager.mark_failed("id2", 500)
        
        stats = manager.get_stats()
        
        assert stats['total'] == 3
        assert stats['active'] == 1
        assert stats['failed'] == 1
        assert stats['cooldown'] == 1
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check functionality."""
        manager = ClientIDManager(["id1", "id2", "id3"])
        
        await manager.mark_failed("id1", 401)
        
        health = await manager.health_check()
        
        assert health['total'] == 3
        assert health['active'] == 2
        assert health['failed'] == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test thread-safe concurrent access."""
        manager = ClientIDManager(["id1", "id2", "id3"], strategy='round-robin')
        
        # Create multiple concurrent tasks
        tasks = [manager.get_active_id() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All tasks should get an ID
        assert len(results) == 10
        assert all(r in ["id1", "id2", "id3"] for r in results)
    
    @pytest.mark.asyncio
    async def test_cooldown_recovery(self):
        """Test that IDs in cooldown can recover."""
        manager = ClientIDManager(["id1"], strategy='failover', cooldown_seconds=0)
        
        # Mark as failed with non-auth error (cooldown)
        await manager.mark_failed("id1", 500)
        assert manager.client_ids[0].status == ClientIDStatus.COOLDOWN
        
        # With 0 cooldown, should be able to retry immediately
        id_retry = await manager.get_active_id()
        assert id_retry == "id1"
        assert manager.client_ids[0].status == ClientIDStatus.ACTIVE


class TestClientIDManagerIntegration:
    """Integration tests for ClientIDManager."""
    
    @pytest.mark.asyncio
    async def test_realistic_scenario(self):
        """Test a realistic usage scenario."""
        manager = ClientIDManager(
            ["id1", "id2", "id3"],
            strategy='failover',
            cooldown_seconds=300
        )
        
        # Normal usage
        id1 = await manager.get_active_id()
        await manager.mark_success(id1)
        assert manager.client_ids[0].success_count == 1
        
        # ID fails
        await manager.mark_failed(id1, 401)
        
        # Switches to next ID
        id2 = await manager.get_active_id()
        assert id2 == "id2"
        await manager.mark_success(id2)
        
        # Stats should reflect the state
        stats = manager.get_stats()
        assert stats['active'] == 2
        assert stats['failed'] == 1
