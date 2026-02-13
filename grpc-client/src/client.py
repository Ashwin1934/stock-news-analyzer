"""
gRPC Client for FinnHub Headlines
Streams headlines to the inference server
"""

import grpc
import logging
import os
import sys
import yaml
import time
import finnhub
from typing import List, Dict, Iterator
from dotenv import load_dotenv

# Add generated proto files to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'generated'))

import headlines_pb2
import headlines_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HeadlinesStreamClient:
    """Manages gRPC connection and headline streaming"""
    
    def __init__(self, config: Dict):
        """Initialize the client with configuration"""
        self.config = config
        self.server_config = config['server']
        self.mode = self.server_config['mode']
        self.finnhub_client = finnhub.Client(api_key=config['finnhub_api_key'])
        self.symbols = config.get('symbols', ['AAPL', 'MSFT'])
        self.poll_interval = config.get('poll_interval', 2)  # seconds
        self.stub = None
        self.channel = None
    
    def _get_server_address(self) -> str:
        """Get server address based on configuration mode"""
        if self.mode == 'uds':
            uds_path = self.server_config['uds_path']
            return f'unix://{uds_path}'
        elif self.mode == 'tcp':
            host = self.server_config.get('host', 'localhost')
            port = self.server_config.get('port', 50051)
            return f'{host}:{port}'
        else:
            raise ValueError(f"Unknown mode: {self.mode}")
    
    def connect(self):
        """Establish connection to gRPC server"""
        address = self._get_server_address()
        logger.info(f"Connecting to server at {address} (mode: {self.mode})")
        
        if self.mode == 'uds':
            # For Unix Domain Sockets
            self.channel = grpc.secure_channel(
                address,
                grpc.local_channel_credentials()
            )
        else:
            # For TCP
            host = self.server_config.get('host', 'localhost')
            port = self.server_config.get('port', 50051)
            self.channel = grpc.insecure_channel(f'{host}:{port}')
        
        self.stub = headlines_pb2_grpc.HeadlineServiceStub(self.channel)
        logger.info("Connected to server successfully")
    
    def _headline_batch_generator(self) -> Iterator[headlines_pb2.HeadlineBatch]:
        """
        Generator that yields headline batches from FinnHub
        Runs continuously, polling every poll_interval seconds
        """
        last_headlines = {symbol: set() for symbol in self.symbols}
        
        while True:
            all_headlines = []
            batch_timestamp = int(time.time() * 1000)  # milliseconds
            
            for symbol in self.symbols:
                try:
                    headlines = self.finnhub_client.company_news(symbol, _from=0, to=9)
                    logger.debug(f"Retrieved {len(headlines)} headlines for {symbol}")
                    
                    for headline_data in headlines:
                        headline_text = headline_data.get('headline', '')
                        timestamp = headline_data.get('datetime', batch_timestamp)
                        source = headline_data.get('source', 'FinnHub')
                        
                        # Create a unique identifier for this headline
                        headline_id = (headline_text, timestamp)
                        
                        # Only include if we haven't seen this exact headline before
                        if headline_id not in last_headlines[symbol]:
                            all_headlines.append(
                                headlines_pb2.HeadlineRequest(
                                    headline=headline_text,
                                    timestamp=timestamp,
                                    symbol=symbol,
                                    source=source
                                )
                            )
                            last_headlines[symbol].add(headline_id)
                    
                    # Keep only recent headlines in memory (last 100 per symbol)
                    if len(last_headlines[symbol]) > 100:
                        # Convert set to list, keep last 100
                        items = list(last_headlines[symbol])
                        last_headlines[symbol] = set(items[-100:])
                        
                except Exception as e:
                    logger.error(f"Error fetching headlines for {symbol}: {e}")
                    continue
            
            if all_headlines:
                logger.info(f"Yielding batch with {len(all_headlines)} new headlines")
                yield headlines_pb2.HeadlineBatch(
                    headlines=all_headlines,
                    batch_timestamp=batch_timestamp
                )
            else:
                logger.debug("No new headlines in this poll")
            
            # Wait before next poll
            time.sleep(self.poll_interval)
    
    def stream_headlines(self):
        """Stream headlines to the server"""
        try:
            logger.info(f"Starting to stream headlines for symbols: {self.symbols}")
            logger.info(f"Poll interval: {self.poll_interval} seconds")
            
            # Call the streaming RPC
            response = self.stub.IngestHeadlines(self._headline_batch_generator())
            
            logger.info(
                f"Streaming complete. "
                f"Processed {response.processed_count} headlines "
                f"across {response.batch_count} batches"
            )
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Error streaming headlines: {e}", exc_info=True)
            raise
    
    def close(self):
        """Close the connection"""
        if self.channel:
            self.channel.close()
            logger.info("Connection closed")


def load_config(profile: str = 'tcp') -> Dict:
    """Load configuration from YAML file"""
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    config_path = os.path.join(config_dir, f'application-{profile}.yaml')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"Loaded configuration from {config_path}")
    return config


def load_finnhub_api_key() -> str:
    """Load FinnHub API key from environment"""
    # Load from .env file
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)
    
    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        raise ValueError(
            "FINNHUB_API_KEY not found in environment. "
            "Please set FINNHUB_API_KEY environment variable or create .env file"
        )
    
    return api_key


def main():
    """Main entry point"""
    profile = os.getenv('APP_PROFILE', 'tcp')
    
    if len(sys.argv) > 1:
        profile = sys.argv[1]
    
    logger.info(f"Starting client with profile: {profile}")
    
    try:
        # Load configuration and API key
        config = load_config(profile)
        api_key = load_finnhub_api_key()
        config['finnhub_api_key'] = api_key
        
        # Create and connect client
        client = HeadlinesStreamClient(config)
        client.connect()
        
        # Start streaming
        client.stream_headlines()
        
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'client' in locals():
            client.close()


if __name__ == '__main__':
    main()
