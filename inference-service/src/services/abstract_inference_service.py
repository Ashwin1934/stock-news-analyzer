from abc import ABC, abstractmethod
from typing import List
import logging

logger = logging.getLogger(__name__)

class InferenceService(ABC):
    """Abstract interface for headline inference models"""
    
    def __init__(self, config):
        """
        Initialize the inference service with configuration
        
        Args:
            config: Configuration object containing model-specific settings
        """
        self.config = config
        self._validate_config()
        logger.info(f"{self.__class__.__name__} initialized")
    
    @abstractmethod
    def _validate_config(self):
        """Validate that the config contains required fields for this implementation"""
        pass
    
    @abstractmethod
    def process_batch(self, headlines: List) -> List[dict]:
        """
        Process a batch of headlines and return inference results
        
        Args:
            headlines: List of HeadlineRequest objects
            
        Returns:
            List of dictionaries containing inference results for each headline
        """
        pass
    
    @abstractmethod
    def _process_single(self, headline_text: str, timestamp: str) -> dict:
        """
        Process a single headline
        
        Args:
            headline_text: The headline text to process
            timestamp: Timestamp of the headline
            
        Returns:
            Dictionary containing inference results
        """
        pass
    
    def cleanup(self):
        """Optional cleanup method for resources (models, connections, etc.)"""
        pass