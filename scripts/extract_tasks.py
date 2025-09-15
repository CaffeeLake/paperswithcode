#!/usr/bin/env python3
"""
Extract complete task hierarchy from PapersWithCode evaluation-tables.json
Creates CSV and JSON files for easy filtering and review.
"""

import json
import csv
from collections import defaultdict
import re

def clean_text(text):
    """Clean up text for CSV/JSON export"""
    if not text:
        return ""

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def infer_area_from_description(description):
    """Infer research area from task description"""
    desc_lower = description.lower()

    # Computer Vision keywords
    cv_keywords = ['image', 'vision', 'visual', 'object detection', 'segmentation', 'ocr',
                   'face recognition', 'pose estimation', 'depth estimation', 'optical']

    # NLP keywords
    nlp_keywords = ['language', 'text', 'nlp', 'speech', 'translation', 'sentiment',
                    'question answering', 'summarization', 'dialogue', 'chatbot']

    # ML/General keywords
    ml_keywords = ['learning', 'classification', 'regression', 'clustering', 'recommendation']

    # Time Series keywords
    ts_keywords = ['time series', 'temporal', 'forecasting', 'sequence']

    # Graph keywords
    graph_keywords = ['graph', 'network', 'node', 'link prediction', 'social']

    # Audio keywords
    audio_keywords = ['audio', 'sound', 'music', 'speech recognition']

    # Robotics keywords
    robotics_keywords = ['robot', 'control', 'navigation', 'manipulation', 'autonomous']

    if any(kw in desc_lower for kw in cv_keywords):
        return "Computer Vision"
    elif any(kw in desc_lower for kw in nlp_keywords):
        return "Natural Language Processing"
    elif any(kw in desc_lower for kw in ts_keywords):
        return "Time Series"
    elif any(kw in desc_lower for kw in graph_keywords):
        return "Graphs"
    elif any(kw in desc_lower for kw in audio_keywords):
        return "Audio"
    elif any(kw in desc_lower for kw in robotics_keywords):
        return "Robotics"
    elif any(kw in desc_lower for kw in ml_keywords):
        return "Machine Learning"
    else:
        return "General"

def extract_tasks(item, parent_name=None, level=0, area='Unknown', full_path=""):
    """Recursively extract tasks from the hierarchy"""
    tasks = []

    if not isinstance(item, dict):
        return tasks

    # Get task name - prefer 'task' field, fallback to description
    task_name = item.get('task')
    if not task_name and item.get('description'):
        # Extract first sentence as task name
        desc_lines = clean_text(item.get('description', '')).split('.')
        task_name = desc_lines[0].strip() if desc_lines else ''

    if not task_name:
        return tasks

    # Clean task name
    task_name = clean_text(task_name)[:150]  # Limit length

    # Build full path for easier understanding
    if full_path:
        current_path = f"{full_path} > {task_name}"
    else:
        current_path = task_name

    # If this is a top-level task, infer area
    if level == 0 and item.get('description'):
        area = infer_area_from_description(item.get('description'))

    # Add current task
    task_info = {
        'task_name': task_name,
        'parent_task': parent_name or '',
        'level': level,
        'area': area,
        'full_path': current_path,
        'description': clean_text(item.get('description', ''))[:300],
        'has_datasets': len(item.get('datasets', [])) > 0,
        'num_datasets': len(item.get('datasets', [])),
        'num_subtasks': len(item.get('subtasks', [])),
        'synonyms': ', '.join(item.get('synonyms', []))
    }

    tasks.append(task_info)

    # Process subtasks recursively
    for subtask in item.get('subtasks', []):
        subtasks = extract_tasks(subtask, task_name, level + 1, area, current_path)
        tasks.extend(subtasks)

    return tasks

def main():
    print("Loading evaluation-tables.json...")

    try:
        with open('/Users/nielsrogge/Documents/python_projecten/paperswithcode/data/evaluation-tables.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return

    print(f"Loaded {len(data)} top-level entries")

    # Extract all tasks
    all_tasks = []

    for i, item in enumerate(data):
        if i % 100 == 0:
            print(f"Processing item {i+1}/{len(data)}")

        tasks = extract_tasks(item)
        all_tasks.extend(tasks)

    print(f"Extracted {len(all_tasks)} total tasks")

    # Group by area for summary
    area_counts = defaultdict(int)
    level_counts = defaultdict(int)

    for task in all_tasks:
        area_counts[task['area']] += 1
        level_counts[task['level']] += 1

    print("\nTasks by Area:")
    for area, count in sorted(area_counts.items()):
        print(f"  {area}: {count} tasks")

    print("\nTasks by Level:")
    for level, count in sorted(level_counts.items()):
        print(f"  Level {level}: {count} tasks")

    # Save to CSV
    csv_path = '/Users/nielsrogge/Documents/python_projecten/paperswithcode/paperswithcode_tasks_overview.csv'
    print(f"\nSaving to CSV: {csv_path}")

    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['task_name', 'parent_task', 'level', 'area', 'full_path',
                     'description', 'has_datasets', 'num_datasets', 'num_subtasks', 'synonyms']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for task in sorted(all_tasks, key=lambda x: (x['area'], x['level'], x['task_name'])):
            writer.writerow(task)

    # Save to JSON (hierarchical structure)
    json_path = '/Users/nielsrogge/Documents/python_projecten/paperswithcode/paperswithcode_tasks_hierarchy.json'
    print(f"Saving to JSON: {json_path}")

    # Group tasks by area for the JSON
    areas_structure = defaultdict(list)

    for task in all_tasks:
        if task['level'] == 0:  # Only top-level tasks
            areas_structure[task['area']].append({
                'name': task['task_name'],
                'description': task['description'],
                'has_datasets': task['has_datasets'],
                'num_datasets': task['num_datasets'],
                'num_subtasks': task['num_subtasks']
            })

    hierarchy = {
        'summary': {
            'total_tasks': len(all_tasks),
            'areas': dict(area_counts),
            'levels': dict(level_counts)
        },
        'areas': dict(areas_structure),
        'all_tasks': all_tasks
    }

    with open(json_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(hierarchy, jsonfile, indent=2, ensure_ascii=False)

    print(f"\nFiles created successfully!")
    print(f"📊 CSV file: {csv_path}")
    print(f"🌳 JSON file: {json_path}")
    print(f"\nUse the CSV file to easily filter tasks in Excel/Google Sheets")
    print(f"Use the JSON file to see the hierarchical structure")

if __name__ == "__main__":
    main()