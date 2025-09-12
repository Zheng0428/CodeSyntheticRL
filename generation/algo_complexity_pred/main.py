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

def parse_queries_from_response(response_text: str) -> List[Dict[str, str]]:
    """
    Parse queries from the formatted LLM response.
    
    Args:
        response_text (str): The LLM response containing formatted queries
    
    Returns:
        List[Dict[str, str]]: List of parsed queries with complexity type and ground truth
    """
    queries = []
    
    if not response_text:
        return queries
    
    # Extract content between QUERIES_START and QUERIES_END
    queries_section_match = re.search(r'===QUERIES_START===(.*?)===QUERIES_END===', response_text, re.DOTALL)
    if not queries_section_match:
        return queries
    
    queries_section = queries_section_match.group(1)
    
    # Find all queries
    query_pattern = r'===QUERY_START===(.*?)===QUERY_END==='
    query_matches = re.findall(query_pattern, queries_section, re.DOTALL)
    
    for query_content in query_matches:
        # Extract QUERY_ID
        query_id_match = re.search(r'QUERY_ID:\s*(\d+)', query_content)
        query_id = query_id_match.group(1) if query_id_match else "unknown"
        
        # Extract COMPLEXITY_TYPE
        complexity_type_match = re.search(r'COMPLEXITY_TYPE:\s*([A-Z]+)', query_content)
        complexity_type = complexity_type_match.group(1) if complexity_type_match else ""
        
        # Extract QUERY (now comes before GROUND_TRUTH)
        query_match = re.search(r'QUERY:\s*(.*?)(?=\s*GROUND_TRUTH:)', query_content, re.DOTALL)
        query = query_match.group(1).strip() if query_match else ""
        
        # Extract GROUND_TRUTH (now comes after QUERY)
        ground_truth_match = re.search(r'GROUND_TRUTH:\s*([^\n]+)', query_content)
        ground_truth = ground_truth_match.group(1).strip() if ground_truth_match else ""
        
        if query and complexity_type and ground_truth:
            queries.append({
                "query_id": query_id,
                "complexity_type": complexity_type,
                "ground_truth": ground_truth,
                "query": query
            })
    
    return queries


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
                "task_id": "algo_complexity_pred",
                "question": basic_question,
                "reward": {
                    "ground_truth": basic_answer,
                    "style": "model"
                },
                "data_source": "oc_leetcode",
                "repo_name": "",
                "extra_info": {
                    "id": f"complexity_{question_id}_basic",
                    "question_id": int(question_id),
                    "leetcode_task_id": leetcode_item.get('task_id', ''),
                    "difficulty": leetcode_item.get('difficulty', ''),
                    "tags": leetcode_item.get('tags', []),
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
                    # Parse the LLM response to extract multiple queries
                    parsed_queries = parse_queries_from_response(response)
                    
                    for parsed_query in parsed_queries:
                        qa_pair = {
                            "task_id": "algo_complexity_pred",
                            "question": parsed_query['query'],
                            "reward": {
                                "ground_truth": parsed_query['ground_truth'],
                                "style": "model"
                            },
                            "data_source": "oc_leetcode",
                            "repo_name": "",
                            "extra_info": {
                                "id": f"complexity_{question_id}_{parsed_query['query_id']}",
                                "question_id": int(question_id),
                                "leetcode_task_id": leetcode_item.get('task_id', ''),
                                "difficulty": leetcode_item.get('difficulty', ''),
                                "tags": leetcode_item.get('tags', []),
                                "type": "algorithm_complexity_prediction",
                                "query_id": parsed_query['query_id'],
                                "complexity_type": parsed_query['complexity_type'],
                                "problem_description": problem_description,
                                "code": code,
                                "original_time_complexity": complexity_info_data.get('time_complexity', ''),
                                "original_space_complexity": complexity_info_data.get('space_complexity', ''),
                                "llm_generated": True
                            }
                        }
                        qa_pairs.append(qa_pair)
                    
                    if i == 0 and parsed_queries:
                        print(f"\nGenerated {len(parsed_queries)} queries from LLM response for problem {question_id}")
                else:
                    print(f"No LLM response for problem {question_id}")
    
    # Print example for first item
    if qa_pairs:
        print("\nExample QA pair:")
        print("=" * 80)
        print(f"Task ID: {qa_pairs[0]['task_id']}")
        print(f"Data Source: {qa_pairs[0]['data_source']}")
        print(f"Question: {qa_pairs[0]['question'][:200]}...")
        print(f"Ground Truth: {qa_pairs[0]['reward']['ground_truth'][:200]}...")
        print(f"Style: {qa_pairs[0]['reward']['style']}")
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
    # qa_pairs = []
    # with open(output_path, 'r') as f:
    #     for data in f:
    #         qa_pairs.append(json.loads(data))
    if qa_pairs:
        print("\nQA pair generation completed successfully!")
        print(f"Generated {len(qa_pairs)} QA pairs")
        
        # Show statistics
        time_complexities = {}
        space_complexities = {}
        complexity_types = {}
        difficulties = {}
        
        for qa in qa_pairs:
            extra_info = qa.get('extra_info', {})
            difficulty = extra_info.get('difficulty', 'Unknown')
            difficulties[difficulty] = difficulties.get(difficulty, 0) + 1
            
            # Handle both basic template and LLM generated
            if extra_info.get('llm_generated', False):
                # LLM generated format with complexity_type and ground_truth
                complexity_type = extra_info.get('complexity_type', 'Unknown')
                ground_truth = qa['reward']['ground_truth']
                
                complexity_types[complexity_type] = complexity_types.get(complexity_type, 0) + 1
                
                if complexity_type == 'TIME':
                    time_complexities[ground_truth] = time_complexities.get(ground_truth, 0) + 1
                elif complexity_type == 'SPACE':
                    space_complexities[ground_truth] = space_complexities.get(ground_truth, 0) + 1
            else:
                # Basic template format with original complexities
                time_comp = extra_info.get('time_complexity', '')
                space_comp = extra_info.get('space_complexity', '')
                
                if time_comp:
                    time_complexities[time_comp] = time_complexities.get(time_comp, 0) + 1
                if space_comp:
                    space_complexities[space_comp] = space_complexities.get(space_comp, 0) + 1
        
        if complexity_types:
            print("\nComplexity type distribution:")
            for comp_type, count in sorted(complexity_types.items()):
                print(f"  {comp_type}: {count}")
        
        if time_complexities:
            print("\nTime complexity distribution:")
            for comp, count in sorted(time_complexities.items()):
                print(f"  {comp}: {count}")
        
        if space_complexities:
            print("\nSpace complexity distribution:")
            for comp, count in sorted(space_complexities.items()):
                print(f"  {comp}: {count}")
        
        print("\nDifficulty distribution:")
        for diff, count in sorted(difficulties.items()):
            print(f"  {diff}: {count}")
    else:
        print("No QA pairs were generated.")
    
    print("\nDone!")


if __name__ == "__main__":
    forward()