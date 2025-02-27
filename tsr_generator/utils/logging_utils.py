import os
import logging
from datetime import datetime

def setup_logging(log_dir='logs', log_prefix='tsr_generation'):
    """
    Setup logging configuration
    
    Args:
        log_dir (str): Directory to store log files
        log_prefix (str): Prefix for log file names
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create a timestamp for the log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'{log_dir}/{log_prefix}_{timestamp}.log'

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    return logging.getLogger(__name__) 