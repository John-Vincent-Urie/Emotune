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


class BaselineTrainer:
    """Loads, cleans, splits, trains, and evaluates the TF-IDF baseline models."""

    def __init__(self, dataset_path: Path | str = DATASET_PATH):
        self.dataset_path = dataset_path
        self.models = build_models()

    def load_data(self):
        raw_df = load_custom_dataset(self.dataset_path)
        cleaned_df, data_report = clean_dataset(raw_df)
        train_df, validation_df, test_df = split_dataset(cleaned_df)
        return train_df, validation_df, test_df, data_report

    def evaluate_model(self, model, train_df, test_df):
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

    def run(self):
        artifacts_dir = ensure_artifacts_dir()
        results_path = artifacts_dir / 'baseline_results.json'

        train_df, validation_df, test_df, data_report = self.load_data()

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
        for model_name, model in self.models.items():
            metrics = self.evaluate_model(model, train_df, test_df)
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

        return results


def main():
    BaselineTrainer().run()


if __name__ == '__main__':
    main()
