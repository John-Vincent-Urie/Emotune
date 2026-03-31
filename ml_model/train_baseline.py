"""Train baseline TF-IDF models for the EmoTune dataset."""
from __future__ import annotations

from pathlib import Path
import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from data_pipeline import (
    DATASET_PATH,
    ensure_artifacts_dir,
    load_custom_dataset,
    clean_dataset,
    split_dataset,
)


def build_models():
    return {
        'tfidf_logistic_regression': Pipeline(
            [
                ('tfidf', TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=10000)),
                ('classifier', LogisticRegression(max_iter=2000, class_weight='balanced')),
            ]
        ),
        'tfidf_linear_svm': Pipeline(
            [
                ('tfidf', TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=10000)),
                ('classifier', LinearSVC(class_weight='balanced')),
            ]
        ),
    }


def evaluate_model(model, train_df, test_df):
    model.fit(train_df['text'], train_df['emotion'])
    predictions = model.predict(test_df['text'])

    labels = sorted(test_df['emotion'].unique())
    return {
        'accuracy': round(float(accuracy_score(test_df['emotion'], predictions)), 4),
        'precision_weighted': round(
            float(precision_score(test_df['emotion'], predictions, average='weighted', zero_division=0)),
            4,
        ),
        'recall_weighted': round(
            float(recall_score(test_df['emotion'], predictions, average='weighted', zero_division=0)),
            4,
        ),
        'f1_weighted': round(
            float(f1_score(test_df['emotion'], predictions, average='weighted', zero_division=0)),
            4,
        ),
        'f1_macro': round(
            float(f1_score(test_df['emotion'], predictions, average='macro', zero_division=0)),
            4,
        ),
        'classification_report': classification_report(
            test_df['emotion'],
            predictions,
            output_dict=True,
            zero_division=0,
        ),
        'confusion_matrix_labels': labels,
        'confusion_matrix': confusion_matrix(
            test_df['emotion'],
            predictions,
            labels=labels,
        ).tolist(),
    }


def main():
    artifacts_dir = ensure_artifacts_dir()
    results_path = artifacts_dir / 'baseline_results.json'

    raw_df = load_custom_dataset(DATASET_PATH)
    cleaned_df, data_report = clean_dataset(raw_df)
    train_df, validation_df, test_df = split_dataset(cleaned_df)

    models = build_models()
    results = {
        'dataset_report': data_report,
        'split_sizes': {
            'train': int(len(train_df)),
            'validation': int(len(validation_df)),
            'test': int(len(test_df)),
        },
        'models': {},
        'best_model': None,
    }

    best_model_name = None
    best_score = -1.0
    for model_name, model in models.items():
        metrics = evaluate_model(model, train_df, test_df)
        results['models'][model_name] = metrics
        if metrics['f1_weighted'] > best_score:
            best_score = metrics['f1_weighted']
            best_model_name = model_name

    results['best_model'] = {
        'name': best_model_name,
        'f1_weighted': best_score,
    }

    results_path.write_text(json.dumps(results, indent=2), encoding='utf-8')

    print("Baseline training complete.")
    print(f"Results written to: {results_path}")
    if best_model_name:
        print(f"Best model: {best_model_name} (weighted F1={best_score:.4f})")


if __name__ == '__main__':
    main()
