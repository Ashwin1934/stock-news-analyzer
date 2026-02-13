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
    # Expect a full config dict; `inference` sub-dict contains model settings
    inference_config = config.get('inference', {})
    # Prefer explicit 'implementation' (used in configs). Fall back to legacy 'model_type'.
    implementation = inference_config.get('implementation') or inference_config.get('model_type')

    if not implementation:
        raise ValueError("Missing 'inference.implementation' (or 'inference.model_type') in configuration")

    if implementation == 'finbert':
        logger.info("Creating FinBERT inference service")
        return FinBertInferenceService(config)
    # Add more model types here as you implement them:
    # elif model_type == 'bert':
    #     return BertInferenceService(config)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")