#!/usr/bin/env python3
"""
Fix area classifications in the PapersWithCode task overview.
Manually map common task names to correct areas.
"""

import pandas as pd


def get_correct_area(task_name, description):
    """Get the correct area for a task based on manual mappings"""

    task_lower = task_name.lower() if pd.notna(task_name) else ""
    desc_lower = description.lower() if pd.notna(description) else ""

    # Manual mappings for common tasks that get misclassified
    audio_tasks = [
        "speech recognition",
        "speech synthesis",
        "speech enhancement",
        "speech separation",
        "audio",
        "sound",
        "music",
        "voice",
        "acoustic",
        "keyword spotting",
        "speaker",
        "audio generation",
        "audio captioning",
        "audio tagging",
        "beat tracking",
        "music generation",
        "speech-to-text",
        "text-to-speech",
    ]

    nlp_tasks = [
        "machine translation",
        "translation",
        "language model",
        "text",
        "nlp",
        "question answering",
        "sentiment",
        "summarization",
        "dialogue",
        "chatbot",
        "named entity recognition",
        "pos tagging",
        "parsing",
        "tokenization",
        "data-to-text",
        "text generation",
        "language understanding",
        "reading comprehension",
    ]

    cv_tasks = [
        "object detection",
        "image classification",
        "segmentation",
        "face recognition",
        "pose estimation",
        "depth estimation",
        "optical flow",
        "image generation",
        "style transfer",
        "super-resolution",
        "image restoration",
        "video",
        "visual",
        "ocr",
        "scene understanding",
    ]

    multimodal_tasks = [
        "audio-visual",
        "lip reading",
        "lipreading",
        "talking face",
        "visual question answering",
        "image captioning",
        "multimodal",
    ]

    time_series_tasks = [
        "time series",
        "forecasting",
        "anomaly detection",
        "sequential",
        "temporal",
    ]

    graph_tasks = [
        "graph",
        "network",
        "node",
        "link prediction",
        "social network",
        "knowledge graph",
    ]

    robotics_tasks = [
        "robot",
        "control",
        "navigation",
        "manipulation",
        "autonomous",
        "planning",
        "reinforcement learning",
        "robotic",
    ]

    # Check for audio tasks first
    if any(kw in task_lower for kw in audio_tasks):
        return "Audio"

    # Check for multimodal tasks (these often get misclassified)
    if any(kw in task_lower for kw in multimodal_tasks):
        return "Multimodal"

    # Check for NLP tasks
    if any(kw in task_lower for kw in nlp_tasks):
        return "Natural Language Processing"

    # Check for Computer Vision tasks
    if any(kw in task_lower for kw in cv_tasks):
        return "Computer Vision"

    # Check for Time Series tasks
    if any(kw in task_lower for kw in time_series_tasks):
        return "Time Series"

    # Check for Graph tasks
    if any(kw in task_lower for kw in graph_tasks):
        return "Graphs"

    # Check for Robotics tasks
    if any(kw in task_lower for kw in robotics_tasks):
        return "Robotics"

    # If no specific match, try description-based inference (improved)
    if "speech" in desc_lower or "audio" in desc_lower or "sound" in desc_lower:
        return "Audio"
    elif "language" in desc_lower or "text" in desc_lower or "nlp" in desc_lower:
        return "Natural Language Processing"
    elif "image" in desc_lower or "visual" in desc_lower or "vision" in desc_lower:
        return "Computer Vision"
    elif "graph" in desc_lower or "network" in desc_lower:
        return "Graphs"
    elif "time" in desc_lower or "temporal" in desc_lower:
        return "Time Series"
    else:
        return "Machine Learning"  # Default for unclear cases


def main():
    print("Loading CSV file...")

    # Load the CSV file
    csv_path = "/Users/nielsrogge/Documents/python_projecten/paperswithcode/paperswithcode_tasks_overview.csv"
    df = pd.read_csv(csv_path)

    print(f"Loaded {len(df)} tasks")

    # Show current area distribution
    print("\nCurrent area distribution:")
    print(df["area"].value_counts())

    # Fix areas
    print("\nFixing area classifications...")
    df["area_corrected"] = df.apply(
        lambda row: get_correct_area(row["task_name"], row["description"]), axis=1
    )

    # Show changes
    changes = df[df["area"] != df["area_corrected"]]
    print(f"\nFixed {len(changes)} misclassified tasks")

    # Show new distribution
    print("\nCorrected area distribution:")
    print(df["area_corrected"].value_counts())

    # Replace the area column
    df["area"] = df["area_corrected"]
    df = df.drop("area_corrected", axis=1)

    # Save corrected file
    corrected_path = "/Users/nielsrogge/Documents/python_projecten/paperswithcode/paperswithcode_tasks_overview_corrected.csv"
    df.to_csv(corrected_path, index=False)

    print(f"\nSaved corrected file: {corrected_path}")

    # Show some examples of changes
    if len(changes) > 0:
        print("\nExamples of corrections made:")
        for _, row in changes.head(10).iterrows():
            print(f"  '{row['task_name']}': {row['area']} → {row['area_corrected']}")


if __name__ == "__main__":
    main()
