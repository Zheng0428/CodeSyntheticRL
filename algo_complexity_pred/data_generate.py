import json
import os
import sys
import argparse
from typing import Dict, Any, Optional

# Add parent directory to path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils import extract_json, read_yaml, get_llm_response, get_llm_responses_batch
    from envs import LEETCODE_PATH
except ImportError:
    print("Could not import functions from utils.py. Make sure it exists in the parent directory.")
    # Fallback implementations would go here if needed
    sys.exit(1)


def process_leetcode_data(limit=1, get_llm_responses=False, output_file=None, 
                        input_file='/mnt/bn/tiktok-mm-5/aiic/users/tianyu/dataset/CodeSyntheticData/merged_leetcode.jsonl',
                        max_retries=3):
    """
    Process LeetCode data and generate complexity prediction prompts.
    
    Args:
        limit (int): Number of problems to process (0 for all)
        get_llm_responses (bool): Whether to send prompts to LLM
        output_file (str): Path to save results
        input_file (str): Path to input data file
        max_retries (int): Maximum retry attempts for failed extractions
    
    Returns:
        list: Processed data with prompts and responses
    """
    template = read_yaml('algo_complexity_pred')
    
    # Try to load existing data from output file first
    existing_data = {}
    if output_file and os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                if output_file.endswith('.json'):
                    existing_data = json.load(f)
                    print(f"Loaded {len(existing_data)} existing entries from {output_file}")
                else:
                    # JSONL format
                    for line in f:
                        item = json.loads(line)
                        if 'question_id' in item:
                            existing_data[str(item['question_id'])] = item
                    print(f"Loaded {len(existing_data)} existing entries from {output_file}")
        except Exception as e:
            print(f"Could not load existing data: {e}")
            existing_data = {}
    
    processed_data = []
    prompts = []
    retry_items = []
    
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
                    
                    question_id = str(result['question_id'])
                    
                    # Check if we already have this data and if complexity_data is valid
                    if question_id in existing_data:
                        existing_item = existing_data[question_id]
                        result = existing_item.copy()  # Use existing data
                        
                        # Check if we need to retry (null or missing complexity_data)
                        complexity_data = result.get('complexity_data')
                        if complexity_data is None and get_llm_responses:
                            retry_items.append((len(processed_data), prompt))
                            prompts.append(prompt)
                    else:
                        # New item, add to prompts if LLM responses requested
                        if get_llm_responses:
                            prompts.append(prompt)
                    
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
    
    # Get LLM responses if requested (batch processing with retry logic)
    if get_llm_responses and prompts:
        retry_count = 0
        
        # Create initial mapping of prompt index to data index
        if not retry_items:
            # For new items (not from existing data), create initial mapping
            prompt_to_data_mapping = []
            prompt_idx = 0
            for data_idx, item in enumerate(processed_data):
                if item.get('question_id') not in existing_data or existing_data.get(str(item.get('question_id')), {}).get('complexity_data') is None:
                    prompt_to_data_mapping.append((data_idx, prompts[prompt_idx] if prompt_idx < len(prompts) else None))
                    prompt_idx += 1
        else:
            prompt_to_data_mapping = retry_items
        
        while retry_count < max_retries and prompts:
            print(f"\nAttempt {retry_count + 1}/{max_retries}: Sending {len(prompts)} prompts to LLM in batch mode...")
            responses = get_llm_responses_batch(
                prompts=prompts,
                temperature=0.7,
                batch_size=100,
                max_concurrency=15,
                show_progress=True
            )
            
            # Process responses and identify items that need retry
            new_retry_items = []
            new_prompts = []
            
            for i, response in enumerate(responses):
                if i < len(prompt_to_data_mapping):
                    data_index, original_prompt = prompt_to_data_mapping[i]
                    
                    if data_index < len(processed_data):
                        processed_data[data_index]['response'] = response
                        
                        # Extract complexity data
                        if response:
                            complexity_data = extract_json(response)
                            processed_data[data_index]['complexity_data'] = complexity_data
                            
                            if limit < 5 and limit != 0:
                                print(f"Extracted complexity for {processed_data[data_index]['task_id']}: {complexity_data}")
                            
                            # If extraction failed, add to retry list
                            if complexity_data is None and retry_count < max_retries - 1:
                                new_retry_items.append((data_index, original_prompt))
                                new_prompts.append(original_prompt)
                        else:
                            # No response, add to retry list
                            if retry_count < max_retries - 1:
                                new_retry_items.append((data_index, original_prompt))
                                new_prompts.append(original_prompt)
            
            # Update for next iteration
            prompt_to_data_mapping = new_retry_items
            prompts = new_prompts
            retry_count += 1
            
            if not prompts:
                print("All items processed successfully!")
                break
            else:
                print(f"Need to retry {len(prompts)} items...")
    
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
                        default=LEETCODE_PATH,
                        help='Input file path')
    parser.add_argument('--max-retries', type=int, default=3, 
                        help='Maximum retry attempts for failed extractions')
    parser.add_argument('--format', type=str, choices=['json', 'jsonl'], 
                        help='Override output format (json: question_id-keyed, jsonl: line-by-line)')
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
        input_file=args.input,
        max_retries=args.max_retries
    )
    
    print("\nDone!")


if __name__ == "__main__":
    main()