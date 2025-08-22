import json
import os
import sys
import argparse
from typing import Dict, Any, Optional

# Add parent directory to path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils import extract_json, read_yaml, get_llm_response
except ImportError:
    print("Could not import functions from utils.py. Make sure it exists in the parent directory.")
    # Fallback implementations would go here if needed
    sys.exit(1)


def process_leetcode_data(limit=1, get_llm_responses=False, output_file=None):
    """
    Process LeetCode data and generate complexity prediction prompts.
    
    Args:
        limit (int): Number of problems to process (0 for all)
        get_llm_responses (bool): Whether to send prompts to LLM
        output_file (str): Path to save results
    
    Returns:
        list: Processed data with prompts and responses
    """
    template = read_yaml('algo_complexity_pred')
    leetcode_path = '/mnt/bn/tiktok-mm-5/aiic/users/tianyu/dataset/CodeSyntheticData/merged_leetcode.jsonl'
    
    processed_data = []
    
    try:
        count = 0
        with open(leetcode_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    
                    # Get the code field (either 'python' or 'python_code_only')
                    code_field = 'python'
                    if code_field not in data and 'python_code_only' in data:
                        code_field = 'python_code_only'
                    
                    # Get the problem description
                    description = data.get('problem_description', '')
                    if not description and 'content' in data:
                        description = data['content']
                    
                    # Format the prompt
                    prompt = template['prompt_template'].format(
                        problem_description=description,
                        code=data.get(code_field, "# No code available")
                    )
                    
                    result = {
                        'task_id': data.get('task_id', ''),
                        'question_id': data.get('question_id', ''),
                        'prompt': prompt
                    }
                    
                    # Get LLM response if requested
                    if get_llm_responses:
                        print(f"\nSending prompt for problem {result['task_id']} to LLM...")
                        response = get_llm_response(prompt, temperature=0.1)
                        result['response'] = response
                        
                        # Extract complexity data
                        if response:
                            complexity_data = extract_json(response)
                            result['complexity_data'] = complexity_data
                            print(f"Extracted complexity: {complexity_data}")
                    
                    processed_data.append(result)
                    
                    if count == 0:
                        print("\nExample prompt:")
                        print("-" * 80)
                        print(prompt)
                        print("-" * 80)
                    
                    count += 1
                    if limit > 0 and count >= limit:
                        break
                        
                except Exception as e:
                    print(f"Error processing entry: {e}")
                    continue
    except Exception as e:
        print(f"Error reading LeetCode data: {e}")
    
    # Save results if output file specified
    if output_file and processed_data:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for item in processed_data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            print(f"Saved {len(processed_data)} processed problems to {output_file}")
        except Exception as e:
            print(f"Error saving to output file: {e}")
    
    return processed_data


def main():
    """Main function to execute the script."""
    parser = argparse.ArgumentParser(description='Process LeetCode problems and get algorithm complexity')
    parser.add_argument('--limit', type=int, default=1, help='Number of problems to process (0 for all)')
    parser.add_argument('--llm', action='store_true', help='Get responses from LLM')
    parser.add_argument('--output', type=str, default='/mnt/bn/tiktok-mm-5/aiic/users/tianyu/CodeSyntheticRL/algo_complexity_pred/results.jsonl', help='Output file path')
    args = parser.parse_args()
    
    args.llm = True
    print("\nProcessing LeetCode data...")
    process_leetcode_data(
        limit=args.limit,
        get_llm_responses=args.llm,
        output_file=args.output
    )
    
    print("\nDone!")


if __name__ == "__main__":
    main()