import json
import os
import sys
import argparse
from typing import Dict, Any, Optional

# Add parent directory to path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils import extract_json, read_yaml, get_llm_response, get_llm_responses_batch
except ImportError:
    print("Could not import functions from utils.py. Make sure it exists in the parent directory.")
    # Fallback implementations would go here if needed
    sys.exit(1)


def process_leetcode_data(limit=1, get_llm_responses=False, output_file=None, 
                        input_file='/mnt/bn/tiktok-mm-5/aiic/users/tianyu/dataset/CodeSyntheticData/merged_leetcode.jsonl'):
    """
    Process LeetCode data and generate complexity prediction prompts.
    
    Args:
        limit (int): Number of problems to process (0 for all)
        get_llm_responses (bool): Whether to send prompts to LLM
        output_file (str): Path to save results
        input_file (str): Path to input data file
    
    Returns:
        list: Processed data with prompts and responses
    """
    template = read_yaml('algo_complexity_pred')
    
    processed_data = []
    prompts = []
    
    try:
        count = 0
        with open(input_file, 'r', encoding='utf-8') as f:
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
                        'question_id': data.get('question_id', '')
                    }
                    
                    processed_data.append(result)
                    
                    if get_llm_responses:
                        prompts.append(prompt)
                    
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
    
    # Get LLM responses if requested (batch processing)
    if get_llm_responses and prompts:
        print(f"\nSending {len(prompts)} prompts to LLM in batch mode...")
        responses = get_llm_responses_batch(
            prompts=prompts,
            temperature=0.7,
            batch_size=100,
            max_concurrency=5,
            show_progress=True
        )
        
        # Add responses to processed_data
        for i, response in enumerate(responses):
            if i < len(processed_data):
                processed_data[i]['response'] = response
                
                # Extract complexity data
                if response:
                    complexity_data = extract_json(response)
                    processed_data[i]['complexity_data'] = complexity_data
                    if limit < 5:
                        print(f"Extracted complexity for {processed_data[i]['task_id']}: {complexity_data}")
    
    # Save results if output file specified
    if output_file and processed_data:
        try:
            # Convert list of items to dictionary with question_id as key
            output_dict = {}
            for item in processed_data:
                question_id = item.get('question_id')
                if question_id:  # Only include items with a valid question_id
                    output_dict[str(question_id)] = item
            
            # Determine file extension
            _, ext = os.path.splitext(output_file)
            
            # Save as a single JSON file
            if ext.lower() == '.json':
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(output_dict, f, ensure_ascii=False, indent=2)
            # Save as JSONL (line-delimited JSON) for backward compatibility
            else:
                with open(output_file, 'w', encoding='utf-8') as f:
                    for item in processed_data:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
            
            print(f"Saved {len(output_dict)} processed problems to {output_file}")
            
            # Generate stats
            total_with_complexity = sum(1 for item in processed_data if item.get('complexity_data'))
            print(f"Problems with complexity data: {total_with_complexity}/{len(processed_data)}")
            
        except Exception as e:
            print(f"Error saving to output file: {e}")
    
    return processed_data


def main():
    """Main function to execute the script."""
    parser = argparse.ArgumentParser(description='Process LeetCode problems and get algorithm complexity')
    parser.add_argument('--limit', type=int, default=1, help='Number of problems to process (0 for all)')
    parser.add_argument('--llm', action='store_true', help='Get responses from LLM')
    parser.add_argument('--output', type=str, 
                        default='/mnt/bn/tiktok-mm-5/aiic/users/tianyu/CodeSyntheticRL/algo_complexity_pred/data/complexity.json', 
                        help='Output file path (.json for question_id-keyed format, .jsonl for line-by-line)')
    parser.add_argument('--input', type=str,
                        default='/mnt/bn/tiktok-mm-5/aiic/users/tianyu/dataset/CodeSyntheticData/merged_leetcode.jsonl',
                        help='Input file path')
    parser.add_argument('--format', type=str, choices=['json', 'jsonl'], 
                        help='Override output format (json: que1stion_id-keyed, jsonl: line-by-line)')
    args = parser.parse_args()
    
    # Ensure the output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")
    
    # Override output file extension if format is specified
    if args.format:
        base, _ = os.path.splitext(args.output)
        args.output = f"{base}.{args.format}"
        print(f"Output format set to {args.format}, file will be saved as {args.output}")
    
    print(f"\nProcessing LeetCode data from {args.input}...")
    process_leetcode_data(
        limit=args.limit,
        get_llm_responses=args.llm,
        output_file=args.output,
        input_file=args.input
    )
    
    print("\nDone!")


if __name__ == "__main__":
    main()