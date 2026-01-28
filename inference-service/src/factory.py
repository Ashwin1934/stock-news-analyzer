import logging
from src.services import FinBertInferenceService, InferenceService

logger = logging.getLogger(__name__)

def create_inference_service(config) -> InferenceService:
    """
    Factory function to create the appropriate inference service based on config
    
    Args:
        config: Configuration dictionary loaded from YAML
        
    Returns:
        An instance of InferenceService
        
    Raises:
        ValueError: If model_type is unknown or missing
    """
    model_type = config.get('inference', {}).get('model_type')
    
    if not model_type:
        raise ValueError("Missing 'inference.model_type' in configuration")
    
    if model_type == 'finbert':
        logger.info("Creating FinBERT inference service")
        return FinBertInferenceService(config)
    # Add more model types here as you implement them:
    # elif model_type == 'bert':
    #     return BertInferenceService(config)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")