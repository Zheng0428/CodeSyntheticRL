import requests
import json
import time
import os
import yaml
import argparse
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List, Union
from tqdm import tqdm
from envs import BASE_URL, API_KEY, MODEL, MAX_TOKENS, SYSTEM_PROMPT

def get_llm_response(prompt: str, temperature: float = 0.7, max_tokens: int = None) -> str:
    """
    Sends a prompt to a large language model and returns the text response.

    Args:
        prompt: The user's question or instruction.
        temperature: Temperature for response randomness (0.0 to 1.0)
        max_tokens: Maximum tokens for the response (uses MAX_TOKENS from env if not provided)

    Returns:
        The text response from the model as a string, or None if the request fails.
    """ 
    if not max_tokens:
        max_tokens = MAX_TOKENS
        
    headers = {
        'Content-Type': 'application/json',
        'X-Api-Key': API_KEY,
        'anthropic-version': '2023-06-01'
    }

    # The payload follows the structure required by the API endpoint.
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "temperature": temperature,
        "messages": [
            {'role': 'user', 'content': prompt}
        ]
    }
    
    # Send request with retry logic
    for retry in range(3):
        try:
            # Make the API call
            response = requests.post(
                BASE_URL,
                headers=headers,
                json=payload,  # Use json parameter to auto-handle serialization
                timeout=600  # 10-minute timeout
            )
            
            # print(f"API Response Status: {response.status_code}")
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    response_text = response_json["choices"][0]["message"]["content"]
                    return response_text

                
                # if "content" in response_json and len(response_json["content"]) > 0:
                #     response_text = response_json["content"][0]["text"]
                #     return response_text
                else:
                    print(f"Unexpected response format: {response_json}")
            
            error_msg = f"API request error: {response.status_code}, {response.text}"
            print(f"{error_msg} - Retrying ({retry+1}/3)")
            
            # Check for specific error codes
            try:
                error_json = response.json()
                if "error" in error_json and error_json["error"].get("code") == '-4003':
                    print("Rate limit or quota exceeded, returning None")
                    return None
            except:
                pass
                
            time.sleep(10.0)
        
        except requests.exceptions.RequestException as e:
            print(f"API request exception: {str(e)} - Retrying ({retry+1}/3)")
            time.sleep(30)
        except Exception as e:
            print(f"Unexpected error: {str(e)} - Retrying ({retry+1}/3)")
            time.sleep(30)
    
    print("All retry attempts failed")
    return None

def extract_json(raw_data: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON data from a raw text response.
    
    Args:
        raw_data (str): The raw text response containing JSON data
        
    Returns:
        Optional[Dict[str, Any]]: Extracted JSON data or None if extraction fails
    """
    try:
        # First try to find JSON inside the markdown code block
        json_markers = ["```json", "```"]
        start_marker = None
        
        for marker in json_markers:
            if marker in raw_data:
                start_marker = marker
                break
        
        if start_marker:
            # Find the content between markers
            start_idx = raw_data.find(start_marker) + len(start_marker)
            end_idx = raw_data.find("```", start_idx)
            
            if end_idx != -1:
                json_content = raw_data[start_idx:end_idx].strip()
                return json.loads(json_content)
        
        # If not found between markers, look for { } in the text
        open_brace_idx = raw_data.find("{")
        if open_brace_idx != -1:
            # Find the matching closing brace
            brace_count = 1
            idx = open_brace_idx + 1
            
            while brace_count > 0 and idx < len(raw_data):
                if raw_data[idx] == "{":
                    brace_count += 1
                elif raw_data[idx] == "}":
                    brace_count -= 1
                idx += 1
            
            if brace_count == 0:
                json_content = raw_data[open_brace_idx:idx].strip()
                return json.loads(json_content)
        
        # Last resort: try to find any valid JSON in the text
        import re
        json_pattern = r'(\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\})'
        matches = re.findall(json_pattern, raw_data)
        
        for match in matches:
            try:
                return json.loads(match)
            except:
                continue
                
        return None
    
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return None
    except Exception as e:
        print(f"Error extracting JSON: {e}")
        return None

def read_yaml(config_path: str = 'default') -> Dict[str, Any]:
    """
    Read a YAML configuration file.
    
    Args:
        config_path (str): Path to config file or config name
        
    Returns:
        Dict[str, Any]: Loaded configuration
    """
    # Try different path options
    possible_paths = [
        f'prompt/{config_path}.yaml',
        f'../prompt/{config_path}.yaml',
        f'/mnt/bn/tiktok-mm-5/aiic/users/tianyu/CodeSyntheticRL/prompt/{config_path}.yaml'
    ]
    
    # Try all possible paths
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                print(f"Error reading YAML from {path}: {e}")
    
    print(f"Warning: Could not find configuration '{config_path}' in any location")
    return {'prompt_template': 'No template found'}

async def _async_llm_request(prompt: str, temperature: float = 0.7, max_tokens: int = None, 
                         session: aiohttp.ClientSession = None, 
                         retry_count: int = 3) -> str:
    """
    Async helper function to send a single request to the LLM API.
    
    Args:
        prompt: The prompt to send
        temperature: Temperature for response randomness
        max_tokens: Maximum tokens for the response
        session: Aiohttp ClientSession to use
        retry_count: Number of retries for failed requests
        
    Returns:
        The text response or None if failed
    """
    if not max_tokens:
        max_tokens = MAX_TOKENS
        
    headers = {
        'Content-Type': 'application/json',
        'X-Api-Key': API_KEY,
        'anthropic-version': '2023-06-01'
    }

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "temperature": temperature,
        "messages": [
            {'role': 'user', 'content': prompt}
        ]
    }
    
    # Need to create our own session if not provided
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
        
    try:
        for retry in range(retry_count):
            try:
                # Make the async API call
                async with session.post(
                    BASE_URL,
                    headers=headers,
                    json=payload,
                    timeout=600  # 10-minute timeout
                ) as response:
                    if response.status == 200:
                        response_json = await response.json()
                        
                        if "choices" in response_json and len(response_json["choices"]) > 0:
                            response_text = response_json["choices"][0]["message"]["content"]
                            return response_text
                        else:
                            error_msg = f"Unexpected response format: {response_json}"
                            print(error_msg)
                    
                    error_msg = f"API request error: {response.status}, {await response.text()}"
                    print(f"{error_msg} - Retrying ({retry+1}/{retry_count})")
                    
                    # Check for specific error codes
                    try:
                        error_json = await response.json()
                        if "error" in error_json and error_json["error"].get("code") == '-4003':
                            print("Rate limit or quota exceeded, returning None")
                            return None
                    except:
                        pass
                    
                    await asyncio.sleep(10.0)
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"API request exception: {str(e)} - Retrying ({retry+1}/{retry_count})")
                await asyncio.sleep(10)
            except Exception as e:
                print(f"Unexpected error: {str(e)} - Retrying ({retry+1}/{retry_count})")
                await asyncio.sleep(10)
                
        print("All retry attempts failed")
        return None
        
    finally:
        # Close the session if we created it
        if close_session:
            await session.close()


async def _process_batch(prompts: List[str], 
                         batch_index: int, 
                         temperature: float = 0.7, 
                         max_tokens: int = None,
                         max_concurrency: int = 5,
                         show_progress: bool = True) -> List[Optional[str]]:
    """
    Process a batch of prompts with limited concurrency.
    
    Args:
        prompts: List of prompts to process
        batch_index: Index of this batch for logging
        temperature: Temperature for response randomness
        max_tokens: Maximum tokens for the response
        max_concurrency: Maximum number of concurrent requests
        show_progress: Whether to show progress bar
        
    Returns:
        List of responses in the same order as prompts
    """
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrency)
    
    # Create shared session for all requests in this batch
    async with aiohttp.ClientSession() as session:
        # Define a function for each request that respects the semaphore
        async def process_single(prompt: str, idx: int) -> tuple:
            async with semaphore:
                response = await _async_llm_request(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    session=session
                )
                return idx, response
        
        # Create tasks for all prompts
        tasks = [process_single(prompt, i) for i, prompt in enumerate(prompts)]
        
        # Set up progress tracking if requested
        if show_progress:
            # Process with progress bar
            responses = [None] * len(prompts)
            for future in tqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc=f"Batch {batch_index}"
            ):
                idx, response = await future
                responses[idx] = response
        else:
            # Process without progress bar
            results = await asyncio.gather(*tasks)
            # Sort results by index
            results.sort(key=lambda x: x[0])
            # Extract responses preserving order
            responses = [result[1] for result in results]
            
        return responses


def get_llm_responses_batch(prompts: List[str], 
                           temperature: float = 0.7, 
                           max_tokens: int = None,
                           batch_size: int = 20,
                           max_concurrency: int = 5,
                           show_progress: bool = True) -> List[Optional[str]]:
    """
    Send multiple prompts to a large language model concurrently and return text responses.
    The responses are returned in the same order as the input prompts.
    
    Args:
        prompts: List of prompts to send to the LLM
        temperature: Temperature for response randomness (0.0 to 1.0)
        max_tokens: Maximum tokens for each response
        batch_size: Number of prompts to process in each batch
        max_concurrency: Maximum number of concurrent requests
        show_progress: Whether to show progress bar
        
    Returns:
        List of text responses in the same order as the prompts, or None for failed requests
    """
    if not prompts:
        return []
    
    # Process prompts in batches with asyncio
    all_responses = []
    
    # Use asyncio to process batches of prompts concurrently
    for batch_idx in range(0, len(prompts), batch_size):
        batch = prompts[batch_idx:batch_idx + batch_size]
        
        # Create and run a new event loop for each batch
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            batch_responses = loop.run_until_complete(
                _process_batch(
                    prompts=batch,
                    batch_index=batch_idx // batch_size + 1,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_concurrency=max_concurrency,
                    show_progress=show_progress
                )
            )
            all_responses.extend(batch_responses)
        finally:
            loop.close()
    
    return all_responses


def main():
    """
    Main function for testing the utils functions.
    """
    parser = argparse.ArgumentParser(description='Test utility functions')
    parser.add_argument('--test', choices=['llm', 'batch', 'yaml', 'json', 'all'], default='all',
                      help='Which test to run (llm, batch, yaml, json, or all)')
    parser.add_argument('--prompt', type=str, default="What is 2+2?",
                      help='Prompt to send to the LLM for testing')
    parser.add_argument('--batch-size', type=int, default=3,
                      help='Number of batch requests to send for testing')
    parser.add_argument('--yaml', type=str, default="algo_complexity_pred",
                      help='YAML file to read for testing')
    args = parser.parse_args()
    
    if args.test in ['yaml', 'all']:
        print("\n=== Testing YAML Reading ===")
        yaml_data = read_yaml(args.yaml)
        print(f"YAML content: {yaml_data.keys()}")
        if 'prompt_template' in yaml_data:
            print(f"Template begins with: {yaml_data['prompt_template'][:50]}...")
    
    if args.test in ['json', 'all']:
        print("\n=== Testing JSON Extraction ===")
        test_json = """
        ```json
        {
          "time_complexity": "O(n)",
          "space_complexity": "O(n)",
          "explanation": "This is a simple test."
        }
        ```
        """
        result = extract_json(test_json)
        print(f"Extracted JSON: {result}")
    
    if args.test in ['llm', 'all'] and API_KEY:
        print("\n=== Testing LLM Response ===")
        print(f"Prompt: {args.prompt}")
        response = get_llm_response(args.prompt, temperature=0.1, max_tokens=100)
        print(f"Response: {response}")
    elif args.test in ['llm', 'all']:
        print("\n=== Skipping LLM Test - API_KEY not set ===")
        print("Set API_KEY environment variable to test LLM functionality")
    
    if args.test in ['batch', 'all'] and API_KEY:
        print("\n=== Testing Batch LLM Responses ===")
        # Create a list of test prompts
        test_prompts = [
            f"{args.prompt} (Question {i+1})" for i in range(args.batch_size)
        ]
        
        print(f"Sending {len(test_prompts)} prompts in batch...")
        responses = get_llm_responses_batch(
            prompts=test_prompts,
            temperature=0.7,
            max_tokens=100,
            max_concurrency=2,
            show_progress=True
        )
        
        # Verify order is preserved
        for i, (prompt, response) in enumerate(zip(test_prompts, responses)):
            print(f"\nPrompt {i+1}: {prompt}")
            print(f"Response {i+1}: {response[:100]}..." if response and len(response) > 100 else f"Response {i+1}: {response}")
    elif args.test in ['batch', 'all']:
        print("\n=== Skipping Batch LLM Test - API_KEY not set ===")
        print("Set API_KEY environment variable to test LLM functionality")
    
    print("\nAll tests completed.")

# Data processing utilities (added for URL processing tasks)
import pandas as pd
from urllib.parse import urlparse
import gc

def extract_root_domain(url):
    """提取根域名（用于URL处理）"""
    if not url or pd.isna(url):
        return None, None
        
    try:
        # 确保URL有协议
        if not url.startswith(('http://', 'https://', 'ftp://', 'ftps://')):
            url = 'http://' + url
            
        parsed = urlparse(url)
        protocol = parsed.scheme
        domain = parsed.netloc.lower()
        
        # 移除端口号
        if ':' in domain:
            domain = domain.split(':')[0]
        
        # 提取根域名（去掉www等前缀）
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            if domain_parts[0] == 'www':
                root_domain = '.'.join(domain_parts[1:])
            else:
                root_domain = domain
        else:
            root_domain = domain
            
        return protocol, root_domain
    except Exception as e:
        return None, None

def get_memory_usage():
    """获取当前内存使用情况（MB）"""
    import psutil
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def force_gc():
    """强制垃圾回收"""
    gc.collect()

def safe_parquet_read_batches(file_path, chunk_size=50000):
    """
    安全的parquet文件分批读取
    返回批次迭代器
    """
    try:
        # 优先使用pyarrow
        import pyarrow.parquet as pq
        parquet_file = pq.ParquetFile(file_path)
        for batch in parquet_file.iter_batches(batch_size=chunk_size):
            yield batch.to_pandas()
    except ImportError:
        # 降级使用pandas
        print(f"警告：未安装pyarrow，使用pandas读取 {file_path}")
        df = pd.read_parquet(file_path)
        total_rows = len(df)
        for start_idx in range(0, total_rows, chunk_size):
            end_idx = min(start_idx + chunk_size, total_rows)
            yield df.iloc[start_idx:end_idx]
        del df
        force_gc()

if __name__ == "__main__":
    main()
