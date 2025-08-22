import requests
import json
import time
import os
import yaml
import argparse
from typing import Dict, Any, Optional, List, Union
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

def main():
    """
    Main function for testing the utils functions.
    """
    parser = argparse.ArgumentParser(description='Test utility functions')
    parser.add_argument('--test', choices=['llm', 'yaml', 'json', 'all'], default='all',
                      help='Which test to run (llm, yaml, json, or all)')
    parser.add_argument('--prompt', type=str, default="What is 2+2?",
                      help='Prompt to send to the LLM for testing')
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
    
    print("\nAll tests completed.")

if __name__ == "__main__":
    main()
