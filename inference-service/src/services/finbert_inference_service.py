from typing import List, Dict
import logging
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from .abstract_inference_service import InferenceService

logger = logging.getLogger(__name__)


class FinBertInferenceService(InferenceService):
    """FinBERT implementation of the inference service for financial sentiment analysis"""
    
    # Sentiment label mapping
    LABEL_MAPPING = {
        0: "positive",
        1: "negative", 
        2: "neutral"
    }
    
    def __init__(self, config):
        """Initialize FinBERT model and tokenizer"""
        self.model = None
        self.tokenizer = None
        self.device = None
        super().__init__(config)  # This calls _validate_config and logs initialization
        self._load_model()
    
    def _validate_config(self):
        """Validate FinBERT-specific configuration"""
        inference_config = self.config.get('inference', {})
        required_fields = ['implementation', 'model_name', 'device', 'batch_size', 'max_sequence_length']
        
        missing_fields = [field for field in required_fields if field not in inference_config]
        if missing_fields:
            raise ValueError(f"Missing required config fields: {', '.join(missing_fields)}")
        
        if inference_config['implementation'] != 'finbert':
            raise ValueError(
                f"Expected implementation 'finbert', got '{inference_config['implementation']}'"
            )
        
        # Validate device
        device = inference_config['device']
        if device not in ['cpu', 'cuda', 'rocm']:
            raise ValueError(f"Device must be 'cpu', 'cuda', or 'rocm', got '{device}'")
        
        # Validate batch_size
        if inference_config['batch_size'] <= 0:
            raise ValueError(f"batch_size must be positive, got {inference_config['batch_size']}")
    
    def _load_model(self):
        """Load FinBERT model and tokenizer into memory"""
        inference_config = self.config['inference']
        model_name = inference_config['model_name']
        device = inference_config['device']
        
        logger.info(f"Loading FinBERT model: {model_name}")
        logger.info(f"Target device: {device}")
        
        try:
            # Load tokenizer
            logger.info("Loading tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            
            # Load model
            logger.info("Loading model weights...")
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            # Set device
            self.device = torch.device(device)
            self.model.to(self.device)
            
            # Set model to evaluation mode
            self.model.eval()
            
            logger.info(f"Model loaded successfully. Device: {self.device}")
            logger.info(f"Model parameters: {sum(p.numel() for p in self.model.parameters()):,}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise RuntimeError(f"Model loading failed: {e}")
    
    def process_batch(self, headlines: List) -> List[Dict]:
        """
        Process a batch of headlines with FinBERT
        
        Args:
            headlines: List of HeadlineRequest objects (with .headline and .timestamp attributes)
            
        Returns:
            List of dictionaries containing inference results
        """
        if not headlines:
            logger.warning("Received empty batch")
            return []
        
        logger.info(f"Processing batch of {len(headlines)} headlines with FinBERT")
        
        # Extract texts and timestamps
        texts = [h.headline for h in headlines]
        timestamps = [h.timestamp for h in headlines]
        
        # Process in batches according to config
        batch_size = self.config['inference']['batch_size']
        all_results = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_timestamps = timestamps[i:i + batch_size]
            
            logger.debug(f"Processing sub-batch {i//batch_size + 1}: {len(batch_texts)} items")
            batch_results = self._process_batch_internal(batch_texts, batch_timestamps)
            all_results.extend(batch_results)
        
        return all_results
    
    def _process_batch_internal(self, texts: List[str], timestamps: List[str]) -> List[Dict]:
        """
        Internal method to process a single batch through the model
        
        Args:
            texts: List of headline texts
            timestamps: List of corresponding timestamps
            
        Returns:
            List of result dictionaries
        """
        max_length = self.config['inference']['max_sequence_length']
        
        # Tokenize the batch
        logger.debug(f"Tokenizing {len(texts)} headlines...")
        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt"
        )
        
        # Move inputs to device
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Run inference
        logger.debug("Running model inference...")
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            
            # Get probabilities
            probabilities = torch.nn.functional.softmax(logits, dim=-1)
            
            # Get predictions
            predicted_classes = torch.argmax(probabilities, dim=-1)
            confidence_scores = torch.max(probabilities, dim=-1).values
        
        # Build results
        results = []
        for idx, (text, timestamp) in enumerate(zip(texts, timestamps)):
            predicted_label = self.LABEL_MAPPING[predicted_classes[idx].item()]
            confidence = confidence_scores[idx].item()
            
            # Get all class probabilities
            probs = probabilities[idx].cpu().numpy()
            
            result = {
                "headline": text,
                "timestamp": timestamp,
                "sentiment": predicted_label,
                "confidence": float(confidence),
                "probabilities": {
                    "positive": float(probs[0]),
                    "negative": float(probs[1]),
                    "neutral": float(probs[2])
                }
            }
            results.append(result)
            
            logger.debug(
                f"Headline: '{text[:50]}...' → {predicted_label} "
                f"(confidence: {confidence:.3f})"
            )
        
        return results
    
    def _process_single(self, headline_text: str, timestamp: str) -> Dict:
        """
        Process a single headline (wrapper around batch processing)
        
        Args:
            headline_text: The headline text to process
            timestamp: Timestamp of the headline
            
        Returns:
            Dictionary containing inference results
        """
        # Create a simple object to match the expected interface
        class HeadlineRequest:
            def __init__(self, headline, timestamp):
                self.headline = headline
                self.timestamp = timestamp
        
        results = self.process_batch([HeadlineRequest(headline_text, timestamp)])
        return results[0] if results else {}
    
    def cleanup(self):
        """Clean up model resources"""
        logger.info("Cleaning up FinBERT resources...")
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        
        # Clear GPU cache if using GPU
        if self.device and self.device.type in ['cuda', 'rocm']:
            if self.device.type == 'cuda':
                torch.cuda.empty_cache()
            elif self.device.type == 'rocm':
                torch.cuda.empty_cache()  # ROCm uses the same interface
        
        logger.info("Cleanup complete")