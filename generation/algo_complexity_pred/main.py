import json
import os
import sys
import argparse
import re
from typing import Dict, Any, Optional, List
import yaml

# Add parent directory to path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils import extract_json, read_yaml, get_llm_response, get_llm_responses_batch, register_forward
except ImportError:
    print("Could not import functions from utils.py. Make sure it exists in the parent directory.")
    # Fallback implementations would go here if needed
    sys.exit(1)

def parse_qa_pairs_from_response(response_text: str) -> List[Dict[str, str]]:
    """
    Parse QA pairs from the formatted LLM response.
    
    Args:
        response_text (str): The LLM response containing formatted QA pairs
    
    Returns:
        List[Dict[str, str]]: List of parsed QA pairs
    """
    qa_pairs = []
    
    if not response_text:
        return qa_pairs
    
    # Extract content between QA_PAIRS_START and QA_PAIRS_END
    qa_section_match = re.search(r'===QA_PAIRS_START===(.*?)===QA_PAIRS_END===', response_text, re.DOTALL)
    if not qa_section_match:
        return qa_pairs
    
    qa_section = qa_section_match.group(1)
    
    # Find all pairs
    pair_pattern = r'===PAIR_START===(.*?)===PAIR_END==='
    pair_matches = re.findall(pair_pattern, qa_section, re.DOTALL)
    
    for pair_content in pair_matches:
        # Extract PAIR_ID
        pair_id_match = re.search(r'PAIR_ID:\s*(\d+)', pair_content)
        pair_id = pair_id_match.group(1) if pair_id_match else "unknown"
        
        # Extract question
        question_match = re.search(r'===QUESTION_START===(.*?)===QUESTION_END===', pair_content, re.DOTALL)
        question = question_match.group(1).strip() if question_match else ""
        
        # Extract answer
        answer_match = re.search(r'===ANSWER_START===(.*?)===ANSWER_END===', pair_content, re.DOTALL)
        answer = answer_match.group(1).strip() if answer_match else ""
        
        if question and answer:
            qa_pairs.append({
                "pair_id": pair_id,
                "question": question,
                "answer": answer
            })
    
    return qa_pairs


def generate_qa_pairs(complexity_data_file=None, leetcode_file=None, output_file=None, limit=0, get_llm_responses=False):
    """
    Generate QA pairs for algorithm complexity prediction.
    
    Args:
        complexity_data_file (str): Path to complexity.json file
        leetcode_file (str): Path to LeetCode data file
        output_file (str): Path to save QA pairs
        limit (int): Number of problems to process (0 for all)
        get_llm_responses (bool): Whether to use LLM to generate questions
    
    Returns:
        list: Generated QA pairs
    """
    # Load complexity data
    complexity_data = {}
    if complexity_data_file and os.path.exists(complexity_data_file):
        try:
            with open(complexity_data_file, 'r', encoding='utf-8') as f:
                complexity_data = json.load(f)
            print(f"Loaded {len(complexity_data)} complexity records from {complexity_data_file}")
        except Exception as e:
            print(f"Error loading complexity data: {e}")
            return []
    else:
        print(f"Complexity data file not found: {complexity_data_file}")
        return []
    
    # Load LeetCode data
    leetcode_data = {}
    if leetcode_file and os.path.exists(leetcode_file):
        try:
            with open(leetcode_file, 'r', encoding='utf-8') as f:
                for line in f:
                    item = json.loads(line)
                    question_id = str(item.get('question_id', ''))
                    if question_id:
                        leetcode_data[question_id] = item
            print(f"Loaded {len(leetcode_data)} LeetCode problems from {leetcode_file}")
        except Exception as e:
            print(f"Error loading LeetCode data: {e}")
            return []
    else:
        print(f"LeetCode data file not found: {leetcode_file}")
        return []
    
    # Load prompt template
    template = read_yaml('algo_complexity_pred')
    if not template or 'prompt_template' not in template:
        print("Error: Could not load prompt template from algo_complexity_pred.yaml")
        return []
    
    # Generate QA pairs
    qa_pairs = []
    count = 0
    prompts = []
    problem_info = []
    
    # First pass: collect all prompts and problem info
    for question_id, complexity_info in complexity_data.items():
        if question_id not in leetcode_data:
            continue
            
        leetcode_item = leetcode_data[question_id]
        complexity_info_data = complexity_info.get('complexity_data')
        
        # Skip if no valid complexity data
        if not complexity_info_data:
            continue
        
        # Get problem description and code
        problem_description = leetcode_item.get('problem_description', '')
        code = leetcode_item.get('completion', '') or leetcode_item.get('python_code_only', '') or leetcode_item.get('python', '')
        
        if not code:
            continue
        
        if get_llm_responses:
            # Prepare LLM prompt for batch processing
            prompt = template['prompt_template'].format(
                problem_description=problem_description,
                code=code,
                time_complexity=complexity_info_data.get('time_complexity', ''),
                space_complexity=complexity_info_data.get('space_complexity', ''),
                explanation=complexity_info_data.get('explanation', '')
            )
            prompts.append(prompt)
            problem_info.append({
                'question_id': question_id,
                'leetcode_item': leetcode_item,
                'complexity_info_data': complexity_info_data,
                'problem_description': problem_description,
                'code': code
            })
        else:
            # Use basic template-based generation
            basic_question = f"Analyze the time and space complexity of the following algorithm solution for: {leetcode_item.get('task_id', '')}.\n\nProblem: {problem_description}\n\nCode:\n```python\n{code}\n```\n\nWhat are the time complexity and space complexity of this solution? Please provide a detailed explanation."
            
            basic_answer = f"**Time Complexity**: {complexity_info_data.get('time_complexity', '')}\n**Space Complexity**: {complexity_info_data.get('space_complexity', '')}\n\n**Explanation**: {complexity_info_data.get('explanation', '')}"
            
            qa_pair = {
                "id": f"complexity_{question_id}_basic",
                "question_id": int(question_id),
                "task_id": leetcode_item.get('task_id', ''),
                "difficulty": leetcode_item.get('difficulty', ''),
                "tags": leetcode_item.get('tags', []),
                "question": basic_question,
                "answer": basic_answer,
                "metadata": {
                    "type": "algorithm_complexity_prediction",
                    "pair_id": "basic",
                    "problem_description": problem_description,
                    "code": code,
                    "time_complexity": complexity_info_data.get('time_complexity', ''),
                    "space_complexity": complexity_info_data.get('space_complexity', ''),
                    "llm_generated": False
                }
            }
            qa_pairs.append(qa_pair)
        
        count += 1
        
        # Limit check
        if limit > 0 and count >= limit:
            break
    
    # Batch process LLM requests if needed
    if get_llm_responses and prompts:
        print(f"\nSending {len(prompts)} prompts to LLM in batch mode...")
        responses = get_llm_responses_batch(
            prompts=prompts,
            temperature=0.7,
            batch_size=100,
            max_concurrency=15,
            show_progress=True
        )
        
        # Process responses and generate QA pairs
        for i, response in enumerate(responses):
            if i < len(problem_info):
                info = problem_info[i]
                question_id = info['question_id']
                leetcode_item = info['leetcode_item']
                complexity_info_data = info['complexity_info_data']
                problem_description = info['problem_description']
                code = info['code']
                
                if response:
                    # Parse the LLM response to extract multiple QA pairs
                    parsed_pairs = parse_qa_pairs_from_response(response)
                    
                    for parsed_pair in parsed_pairs:
                        qa_pair = {
                            "id": f"complexity_{question_id}_{parsed_pair['pair_id']}",
                            "question_id": int(question_id),
                            "task_id": leetcode_item.get('task_id', ''),
                            "difficulty": leetcode_item.get('difficulty', ''),
                            "tags": leetcode_item.get('tags', []),
                            "question": parsed_pair['question'],
                            "answer": parsed_pair['answer'],
                            "metadata": {
                                "type": "algorithm_complexity_prediction",
                                "pair_id": parsed_pair['pair_id'],
                                "problem_description": problem_description,
                                "code": code,
                                "original_time_complexity": complexity_info_data.get('time_complexity', ''),
                                "original_space_complexity": complexity_info_data.get('space_complexity', ''),
                                "llm_generated": True
                            }
                        }
                        qa_pairs.append(qa_pair)
                    
                    if i == 0 and parsed_pairs:
                        print(f"\nGenerated {len(parsed_pairs)} QA pairs from LLM response for problem {question_id}")
                else:
                    print(f"No LLM response for problem {question_id}")
    
    # Print example for first item
    if qa_pairs:
        print("\nExample QA pair:")
        print("=" * 80)
        print(f"Question ID: {qa_pairs[0]['question_id']}")
        print(f"Task ID: {qa_pairs[0]['task_id']}")
        print(f"Question: {qa_pairs[0]['question'][:200]}...")
        print(f"Answer: {qa_pairs[0]['answer'][:200]}...")
        print("=" * 80)
    
    print(f"Generated {len(qa_pairs)} QA pairs")
    
    # Save results
    if output_file and qa_pairs:
        try:
            # Ensure the output directory exists
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"Created output directory: {output_dir}")
            
            # Determine file extension and save accordingly
            _, ext = os.path.splitext(output_file)
            
            if ext.lower() == '.jsonl':
                # Save as JSONL
                with open(output_file, 'w', encoding='utf-8') as f:
                    for qa_pair in qa_pairs:
                        f.write(json.dumps(qa_pair, ensure_ascii=False) + '\n')
            else:
                # Save as JSON
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
            
            print(f"Saved {len(qa_pairs)} QA pairs to {output_file}")
            
        except Exception as e:
            print(f"Error saving QA pairs: {e}")
    
    return qa_pairs

@register_forward("algo_complexity_pred")
def forward(args):
    """Main function to execute the script."""
    input_path=args['input_path']
    output_path=args['output_path']
    
    print(f"Generating QA pairs for algorithm complexity prediction...")
    print(f"Complexity data: {args['complexity_data']}")
    print(f"LeetCode data: {input_path}")
    print(f"Output file: {output_path}")
    print(f"Limit: {args['limit'] if args['limit'] > 0 else 'No limit'}")
    print(f"LLM generation: {'Enabled' if args['llm'] else 'Disabled (basic template)'}")
    
    qa_pairs = generate_qa_pairs(
        complexity_data_file=args['complexity_data'],
        leetcode_file=input_path,
        output_file=output_path,
        limit=args['limit'],
        get_llm_responses=args['llm']
    )
    
    if qa_pairs:
        print("\nQA pair generation completed successfully!")
        print(f"Generated {len(qa_pairs)} QA pairs")
        
        # Show statistics
        complexities = {}
        difficulties = {}
        for qa in qa_pairs:
            time_comp = qa['metadata']['time_complexity']
            difficulty = qa.get('difficulty', 'Unknown')
            
            complexities[time_comp] = complexities.get(time_comp, 0) + 1
            difficulties[difficulty] = difficulties.get(difficulty, 0) + 1
        
        print("\nTime complexity distribution:")
        for comp, count in sorted(complexities.items()):
            print(f"  {comp}: {count}")
        
        print("\nDifficulty distribution:")
        for diff, count in sorted(difficulties.items()):
            print(f"  {diff}: {count}")
    else:
        print("No QA pairs were generated.")
    
    print("\nDone!")


if __name__ == "__main__":
    forward()