"""Docker image builder and registry pusher"""

import logging
import docker
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DockerBuilder:
    """Builds and pushes Docker images for task instances"""
    
    def __init__(self):
        """Initialize Docker client"""
        try:
            self.client = docker.from_env()
            logger.info("Docker client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise
    
    def build_image(
        self,
        task_dir: Path,
        image_name: str,
        dockerfile_path: str = "Dockerfile"
    ) -> bool:
        """
        Build Docker image for task instance.
        
        Args:
            task_dir: Directory containing Dockerfile and eval_script.sh
            image_name: Full image name with tag
            dockerfile_path: Path to Dockerfile relative to task_dir
            
        Returns:
            True if build successful, False otherwise
        """
        try:
            logger.info(f"Building Docker image: {image_name}")
            logger.info(f"Build context: {task_dir}")
            
            # Build image
            image, build_logs = self.client.images.build(
                path=str(task_dir),
                dockerfile=dockerfile_path,
                tag=image_name,
                rm=True,  # Remove intermediate containers
                forcerm=True,  # Always remove intermediate containers
            )
            
            # Log build output
            for log in build_logs:
                if 'stream' in log:
                    logger.debug(log['stream'].strip())
                elif 'error' in log:
                    logger.error(log['error'].strip())
                    return False
            
            logger.info(f"Successfully built image: {image_name}")
            return True
            
        except docker.errors.BuildError as e:
            logger.error(f"Build error: {e}")
            for log in e.build_log:
                if 'stream' in log:
                    logger.error(log['stream'].strip())
            return False
        except Exception as e:
            logger.error(f"Failed to build image: {e}")
            return False
    
    def push_image(self, image_name: str) -> bool:
        """
        Push Docker image to registry.
        
        Args:
            image_name: Full image name with tag
            
        Returns:
            True if push successful, False otherwise
        """
        try:
            logger.info(f"Pushing Docker image: {image_name}")
            
            # Push image
            push_logs = self.client.images.push(
                image_name,
                stream=True,
                decode=True
            )
            
            # Log push output
            for log in push_logs:
                if 'status' in log:
                    logger.debug(f"{log['status']}: {log.get('progress', '')}")
                elif 'error' in log:
                    logger.error(log['error'])
                    return False
            
            logger.info(f"Successfully pushed image: {image_name}")
            return True
            
        except docker.errors.APIError as e:
            logger.error(f"API error while pushing image: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to push image: {e}")
            return False
    
    def build_and_push(
        self,
        task_dir: Path,
        image_name: str,
        push: bool = True
    ) -> bool:
        """
        Build and optionally push Docker image.
        
        Args:
            task_dir: Directory containing Dockerfile
            image_name: Full image name with tag
            push: Whether to push to registry
            
        Returns:
            True if successful, False otherwise
        """
        # Build image
        if not self.build_image(task_dir, image_name):
            return False
        
        # Push image if requested
        if push:
            if not self.push_image(image_name):
                return False
        
        return True
    
    def verify_image(self, image_name: str) -> bool:
        """
        Verify that Docker image exists locally.
        
        Args:
            image_name: Full image name with tag
            
        Returns:
            True if image exists, False otherwise
        """
        try:
            self.client.images.get(image_name)
            logger.info(f"Image verified: {image_name}")
            return True
        except docker.errors.ImageNotFound:
            logger.warning(f"Image not found: {image_name}")
            return False
        except Exception as e:
            logger.error(f"Error verifying image: {e}")
            return False
    
    def test_image(self, image_name: str, eval_script_path: str = "/eval_script.sh") -> bool:
        """
        Test Docker image by running eval script.
        
        Args:
            image_name: Full image name with tag
            eval_script_path: Path to eval script inside container
            
        Returns:
            True if eval script passes, False otherwise
        """
        try:
            logger.info(f"Testing image: {image_name}")
            
            # Run container with eval script
            container = self.client.containers.run(
                image_name,
                command=eval_script_path,
                detach=True,
                remove=True
            )
            
            # Wait for container to finish
            result = container.wait()
            exit_code = result['StatusCode']
            
            # Get logs
            logs = container.logs().decode('utf-8')
            logger.info(f"Container logs:\n{logs}")
            
            if exit_code == 0:
                logger.info(f"Image test passed: {image_name}")
                return True
            else:
                logger.warning(f"Image test failed with exit code {exit_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error testing image: {e}")
            return False
    
    def cleanup_image(self, image_name: str) -> bool:
        """
        Remove Docker image from local system.
        
        Args:
            image_name: Full image name with tag
            
        Returns:
            True if removed, False otherwise
        """
        try:
            self.client.images.remove(image_name, force=True)
            logger.info(f"Removed image: {image_name}")
            return True
        except docker.errors.ImageNotFound:
            logger.warning(f"Image not found: {image_name}")
            return False
        except Exception as e:
            logger.error(f"Error removing image: {e}")
            return False
    
    def get_image_info(self, image_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about Docker image.
        
        Args:
            image_name: Full image name with tag
            
        Returns:
            Dictionary with image info or None
        """
        try:
            image = self.client.images.get(image_name)
            return {
                'id': image.id,
                'tags': image.tags,
                'size': image.attrs['Size'],
                'created': image.attrs['Created'],
            }
        except docker.errors.ImageNotFound:
            logger.warning(f"Image not found: {image_name}")
            return None
        except Exception as e:
            logger.error(f"Error getting image info: {e}")
            return None
    
    def login(self, username: str, password: str, registry: str = "docker.io") -> bool:
        """
        Login to Docker registry.
        
        Args:
            username: Registry username
            password: Registry password
            registry: Registry URL
            
        Returns:
            True if login successful, False otherwise
        """
        try:
            self.client.login(
                username=username,
                password=password,
                registry=registry
            )
            logger.info(f"Successfully logged in to {registry}")
            return True
        except Exception as e:
            logger.error(f"Failed to login to registry: {e}")
            return False
