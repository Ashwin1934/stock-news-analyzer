"""
gRPC Inference Server for Financial News Headlines
Streaming batches for efficient processing
"""

import grpc
from concurrent import futures
import logging
import os
import sys
import yaml
from src.factory import create_inference_service

# Add generated proto files to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'generated'))

# Generated modules are named `headlines_pb2`/`headlines_pb2_grpc`.
# Import them under the legacy names used throughout this file.
import headlines_pb2 as headline_pb2
import headlines_pb2_grpc as headline_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HeadlineServicer(headline_pb2_grpc.HeadlineServiceServicer):
    """gRPC servicer for headline ingestion"""
    
    def __init__(self, inference_service):
        self.inference_service = inference_service
        self.total_headlines = 0
        self.batch_count = 0
    
    def IngestHeadlines(self, request_iterator, context):
        """
        Ingest stream of headline batches
        
        Each request in the stream contains a batch of headlines
        from a single FinnHub API call.
        """
        try:
            for batch_request in request_iterator:
                headlines = batch_request.headlines
                batch_timestamp = batch_request.batch_timestamp
                
                logger.info(
                    f"Received batch {self.batch_count + 1} "
                    f"with {len(headlines)} headlines "
                    f"(timestamp: {batch_timestamp})"
                )
                
                # Process the entire batch
                self.inference_service.process_batch(headlines)
                
                self.total_headlines += len(headlines)
                self.batch_count += 1
                
                # Log progress every 10 batches
                if self.batch_count % 10 == 0:
                    logger.info(
                        f"Progress: {self.batch_count} batches, "
                        f"{self.total_headlines} headlines processed"
                    )
            
            logger.info(
                f"Stream complete. Processed {self.total_headlines} headlines "
                f"across {self.batch_count} batches"
            )
            
            return headline_pb2.StreamResponse(
                processed_count=self.total_headlines,
                batch_count=self.batch_count
            )
            
        except Exception as e:
            logger.error(f"Error processing stream: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return headline_pb2.StreamResponse()


def load_config(profile='uds'):
    """Load configuration from YAML file"""
    # Support both relative and absolute paths
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    config_path = os.path.join(config_dir, f'application-{profile}.yaml')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"Loaded configuration from {config_path}")
    return config


def serve(config):
    """Start the gRPC server"""
    
    server_config = config['server']
    mode = server_config['mode']
    
    # Initialize inference service (pass full configuration dict)
    inference_service = create_inference_service(config)
    
    # Create gRPC server
    max_workers = server_config.get('max_workers', 10)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ('grpc.max_send_message_length', server_config.get('max_message_size', 10 * 1024 * 1024)),
            ('grpc.max_receive_message_length', server_config.get('max_message_size', 10 * 1024 * 1024)),
        ]
    )
    
    # Add servicer
    servicer = HeadlineServicer(inference_service)
    headline_pb2_grpc.add_HeadlineServiceServicer_to_server(servicer, server)
    
    # Configure address based on mode
    if mode == 'uds':
        uds_path = server_config['uds_path']
        
        # Clean up existing socket
        if os.path.exists(uds_path):
            os.remove(uds_path)
        
        address = f'unix://{uds_path}'
        server.add_insecure_port(address)
        logger.info(f"Server listening on Unix Domain Socket: {uds_path}")
        
    elif mode == 'tcp':
        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 50051)
        
        address = f'{host}:{port}'
        server.add_insecure_port(address)
        logger.info(f"Server listening on TCP: {address}")
    
    else:
        raise ValueError(f"Unknown mode: {mode}")
    
    # Start server
    server.start()
    logger.info("Server started successfully")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop(grace=5)
        if mode == 'uds' and os.path.exists(server_config.get('uds_path', '')):
            os.remove(server_config['uds_path'])


if __name__ == '__main__':
    profile = os.getenv('APP_PROFILE', 'uds')
    
    if len(sys.argv) > 1:
        profile = sys.argv[1]
    
    logger.info(f"Starting with profile: {profile}")
    
    config = load_config(profile)
    serve(config)