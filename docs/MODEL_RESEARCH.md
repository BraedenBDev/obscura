# PII Detection Model Research & Continuous Improvement Architecture

> Research conducted: January 2026
> Current model: `urchade/gliner_multi_pii-v1`

---

## Table of Contents

1. [GLiNER PII Models Comparison](#gliner-pii-models-comparison)
2. [Model Recommendations](#model-recommendations)
3. [Fine-Tuning GLiNER](#fine-tuning-gliner)
4. [Continuous Improvement Architecture](#continuous-improvement-architecture)
5. [Implementation Roadmap](#implementation-roadmap)
6. [Resources & Sources](#resources--sources)

---

## GLiNER PII Models Comparison

### Performance Benchmarks

| Model | F1 Score | Precision | Recall | Size | License |
|-------|----------|-----------|--------|------|---------|
| **gretelai/gretel-gliner-bi-large-v1.0** | **0.95** | 0.99 | 0.93 | ~1GB | Apache 2.0 |
| gretelai/gretel-gliner-bi-base-v1.0 | 0.95 | 0.98 | 0.92 | ~500MB | Apache 2.0 |
| knowledgator/gliner-pii-large-v1.0 | 0.83 | 0.87 | 0.79 | ~1GB | Apache 2.0 |
| **knowledgator/gliner-pii-base-v1.0** | **0.81** | 0.79 | 0.83 | 330MB | Apache 2.0 |
| nvidia/gliner-PII | 0.87* | - | - | 570M params | NVIDIA Open |
| E3-JSI/gliner-multi-pii-domains-v1 | ~0.77 | - | - | 0.3B | Apache 2.0 |
| urchade/gliner_multi_pii-v1 (current) | 0.77 | 0.79 | 0.75 | ~0.3B | Apache 2.0 |

*NVIDIA score on their Nemotron benchmark

### Model Details

#### 1. Gretel Models (Highest Performance)
- **URL**: https://huggingface.co/gretelai/gretel-gliner-bi-large-v1.0
- **Base**: `knowledgator/gliner-bi-large-v1.0`
- **Training Data**: `gretelai/gretel-pii-masking-en-v1` (60k synthetic records)
- **Entity Types**: 41 categories
- **Strengths**: Highest F1/precision, production-grade
- **Weaknesses**: Larger model, English-focused, fewer entity types

#### 2. Knowledgator Models (Best Value)
- **URL**: https://huggingface.co/knowledgator/gliner-pii-base-v1.0
- **Entity Types**: 60+ categories
- **Formats**: PyTorch, ONNX (FP16: 330MB, UINT8: 197MB)
- **Strengths**: Same size as current model, more entity types, ONNX support
- **Weaknesses**: Lower F1 than Gretel

#### 3. NVIDIA Model (Enterprise-Grade)
- **URL**: https://huggingface.co/nvidia/gliner-PII
- **Release**: October 2025
- **Training Data**: `nvidia/nemotron-pii` (200k records, 50+ industries)
- **Entity Types**: 55+ PII/PHI categories
- **Strengths**: Newest, best documentation, multi-industry support
- **Weaknesses**: NVIDIA license restrictions

#### 4. E3-JSI Model (Multi-Domain)
- **URL**: https://huggingface.co/E3-JSI/gliner-multi-pii-domains-v1
- **Base**: Fine-tuned from `urchade/gliner_multi_pii-v1`
- **Languages**: 9 languages supported
- **Strengths**: Multi-lingual, domain-specific training
- **Weaknesses**: Similar performance to base model

### Model Lineage

```
urchade/gliner_multi-v2.1 (base GLiNER)
        │
        ├── urchade/gliner_multi_pii-v1 (PII fine-tune)
        │       │
        │       └── E3-JSI/gliner-multi-pii-domains-v1
        │
        └── urchade/gliner_large-v2.1
                │
                └── knowledgator/gliner-bi-large-v1.0
                        │
                        ├── gretelai/gretel-gliner-bi-large-v1.0
                        │
                        └── nvidia/gliner-PII (also uses Gretel data)
```

---

## Model Recommendations

### Option A: Quick Win (Recommended First Step)
**Switch to `knowledgator/gliner-pii-base-v1.0`**

```python
# config.py change
DEFAULT_MODEL = "knowledgator/gliner-pii-base-v1.0"
```

- ~5% F1 improvement (0.77 → 0.81)
- Same model size (330MB)
- Better recall (0.83 vs 0.75) = fewer missed PIIs
- ONNX support for faster inference
- Drop-in replacement

### Option B: Maximum Accuracy
**Switch to `gretelai/gretel-gliner-bi-large-v1.0`**

- ~18% F1 improvement (0.77 → 0.95)
- Requires more memory (~1GB)
- Need to adjust label list to match their 41 categories
- Best for accuracy-critical applications

### Option C: Enterprise Features
**Switch to `nvidia/gliner-PII`**

- Newest model with comprehensive documentation
- Strong US + international ID format support
- 55+ entity categories
- Consider for regulated industries (HIPAA, GDPR)

---

## Fine-Tuning GLiNER

### Training Data Format

```python
train_data = [
    {
        "tokenized_text": ["John", "Smith", "lives", "at", "123", "Main", "St", "."],
        "ner": [
            [0, 1, "person"],      # "John Smith" - indices 0-1
            [4, 6, "address"]      # "123 Main St" - indices 4-6
        ]
    },
    {
        "tokenized_text": ["Email", ":", "john@example.com"],
        "ner": [
            [2, 2, "email"]        # "john@example.com" - index 2
        ]
    }
]
```

### Method 1: Manual Fine-Tuning

```bash
# Clone GLiNER repository
git clone https://github.com/urchade/GLiNER.git
cd GLiNER

# Install dependencies
pip install -r requirements.txt

# Prepare your data in the format above, then:
python train.py --config configs/config.yaml
```

**Training Configuration** (`config.yaml`):
```yaml
model:
  name: "knowledgator/gliner-pii-base-v1.0"

training:
  num_steps: 30000
  train_batch_size: 8
  eval_every: 5000
  warmup_ratio: 0.1
  scheduler_type: "cosine"
  lr_encoder: 1e-5
  lr_others: 5e-5

data:
  train_path: "data/train.json"
  val_path: "data/val.json"
```

### Method 2: Synthetic Data Generation + Fine-Tuning

```bash
pip install gliner-finetune
```

```python
from gliner_finetune import generate, convert, train_model

# 1. Define example data with entity types
examples = [
    {
        "text": "Contact John Smith at john@example.com",
        "entities": [
            {"text": "John Smith", "label": "person"},
            {"text": "john@example.com", "label": "email"}
        ]
    }
]

entity_types = ["person", "email", "phone", "ssn", "address"]

# 2. Generate synthetic variations using GPT
# Requires OPENAI_API_KEY in .env file
generate(examples, entity_types, output_file="synthetic_data.json")

# 3. Convert to training format (80/20 train/val split)
convert("synthetic_data.json", output_dir="data/")

# 4. Fine-tune the model
train_model(
    base_model="knowledgator/gliner-pii-base-v1.0",
    data_dir="data/",
    output_dir="models/pii-shield-custom"
)
```

### Method 3: Using NVIDIA's Approach

```python
from datasets import load_dataset

# Load NVIDIA's high-quality synthetic dataset
dataset = load_dataset("nvidia/nemotron-pii")

# Dataset structure:
# - 200k records across 50+ industries
# - Span-level annotations with start/end positions
# - 55+ PII/PHI entity types

# Convert to GLiNER format and train
def convert_nemotron_to_gliner(record):
    tokens = record["text"].split()
    ner = []
    for span in record["spans"]:
        # Convert character offsets to token indices
        start_token = len(record["text"][:span["start"]].split())
        end_token = len(record["text"][:span["end"]].split()) - 1
        ner.append([start_token, end_token, span["label"]])
    return {"tokenized_text": tokens, "ner": ner}
```

---

## Continuous Improvement Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      PII SHIELD SYSTEM                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │ User Input  │───▶│  GLiNER     │───▶│ Detection   │          │
│  │ (Text)      │    │  Model      │    │ Results     │          │
│  └─────────────┘    └─────────────┘    └──────┬──────┘          │
│                                               │                  │
│                     ┌─────────────────────────▼──────┐           │
│                     │     Confidence Check           │           │
│                     │  (threshold < 0.7 = uncertain) │           │
│                     └─────────────────────────┬──────┘           │
│                                               │                  │
│         ┌────────────────────┬────────────────┘                  │
│         ▼                    ▼                                   │
│  ┌─────────────┐      ┌─────────────┐                           │
│  │ High Conf   │      │ Low Conf    │                           │
│  │ Auto-accept │      │ Queue for   │                           │
│  │             │      │ Review      │                           │
│  └─────────────┘      └──────┬──────┘                           │
│                              │                                   │
│                              ▼                                   │
│                     ┌─────────────┐                              │
│                     │  Argilla    │  ← Human Review UI           │
│                     │  Dashboard  │                              │
│                     └──────┬──────┘                              │
│                            │                                     │
│                            ▼                                     │
│                     ┌─────────────┐                              │
│                     │  Feedback   │  ← Corrections stored        │
│                     │  Database   │                              │
│                     └──────┬──────┘                              │
│                            │                                     │
│         ┌──────────────────┴──────────────────┐                 │
│         ▼                                      ▼                 │
│  ┌─────────────┐                      ┌─────────────┐            │
│  │ Weekly      │                      │ Synthetic   │            │
│  │ Fine-tune   │◀─────────────────────│ Data Gen    │            │
│  │ Job         │                      │ (GPT-based) │            │
│  └─────────────┘                      └─────────────┘            │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ Updated     │───▶ Deploy to production                       │
│  │ Model       │                                                │
│  └─────────────┘                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Component 1: Feedback Collection (Chrome Extension)

```javascript
// pii-widget.js - Add feedback collection

const FeedbackCollector = {
    // Store pending feedback
    pendingFeedback: [],

    // Record when user corrects a detection
    recordCorrection(originalText, detectedEntities, userCorrections) {
        const feedback = {
            id: crypto.randomUUID(),
            timestamp: Date.now(),
            text: originalText,
            model_predictions: detectedEntities,
            user_corrections: userCorrections,
            correction_type: this.classifyCorrection(detectedEntities, userCorrections)
        };

        this.pendingFeedback.push(feedback);
        this.syncToServer();
    },

    // Classify the type of correction
    classifyCorrection(predicted, corrected) {
        const predictedSet = new Set(predicted.map(e => `${e.start}-${e.end}-${e.label}`));
        const correctedSet = new Set(corrected.map(e => `${e.start}-${e.end}-${e.label}`));

        const added = corrected.filter(e => !predictedSet.has(`${e.start}-${e.end}-${e.label}`));
        const removed = predicted.filter(e => !correctedSet.has(`${e.start}-${e.end}-${e.label}`));

        return {
            false_negatives: added,    // Model missed these
            false_positives: removed   // Model incorrectly flagged these
        };
    },

    // Sync feedback to backend
    async syncToServer() {
        if (this.pendingFeedback.length === 0) return;

        try {
            await fetch('http://localhost:5001/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ feedback: this.pendingFeedback })
            });
            this.pendingFeedback = [];
        } catch (err) {
            console.error('[Feedback] Sync failed:', err);
        }
    }
};
```

### Component 2: Backend Feedback API

```python
# api_server.py - Add feedback endpoint

from datetime import datetime
import json

FEEDBACK_FILE = "feedback_data.jsonl"

@app.route('/api/feedback', methods=['POST'])
def collect_feedback():
    """Collect user corrections for model improvement."""
    data = request.json
    feedback_items = data.get('feedback', [])

    # Append to JSONL file (one JSON object per line)
    with open(FEEDBACK_FILE, 'a') as f:
        for item in feedback_items:
            item['received_at'] = datetime.utcnow().isoformat()
            f.write(json.dumps(item) + '\n')

    # Calculate confidence for active learning
    for item in feedback_items:
        if item.get('correction_type'):
            fn_count = len(item['correction_type'].get('false_negatives', []))
            fp_count = len(item['correction_type'].get('false_positives', []))

            # Flag high-value samples for review
            if fn_count > 0 or fp_count > 0:
                queue_for_review(item)

    return jsonify({
        'status': 'success',
        'items_received': len(feedback_items)
    })

def queue_for_review(item):
    """Add to Argilla review queue if available."""
    try:
        import argilla as rg

        record = rg.Record(
            fields={"text": item['text']},
            suggestions=[
                rg.Suggestion(
                    question_name="pii_entities",
                    value=item['model_predictions']
                )
            ],
            metadata={
                "source": "user_correction",
                "timestamp": item['timestamp']
            }
        )

        rg.log(record, name="pii-review-queue")
    except ImportError:
        pass  # Argilla not installed
```

### Component 3: Argilla Setup

```python
# scripts/setup_argilla.py

import argilla as rg

# Connect to Argilla server
rg.init(
    api_url="http://localhost:6900",
    api_key="your-api-key"
)

# Define PII entity labels
PII_LABELS = [
    "person", "email", "phone", "ssn", "address",
    "credit_card", "iban", "passport", "date_of_birth",
    "national_id", "driver_license", "ip_address"
]

# Create dataset settings
settings = rg.Settings(
    fields=[
        rg.TextField(name="text", title="Input Text")
    ],
    questions=[
        rg.SpanQuestion(
            name="pii_entities",
            title="Mark all PII entities",
            field="text",
            labels=PII_LABELS,
            allow_overlapping=False
        )
    ],
    metadata=[
        rg.TermsMetadataProperty(name="source"),
        rg.IntegerMetadataProperty(name="confidence_score")
    ]
)

# Create the review dataset
dataset = rg.Dataset(
    name="pii-review-queue",
    workspace="pii-shield",
    settings=settings
)
dataset.create()

print("Argilla dataset created: pii-review-queue")
```

### Component 4: Automated Retraining Pipeline

```python
# scripts/retrain_model.py

import json
import argilla as rg
from gliner import GLiNER
from gliner.training import Trainer, TrainingArguments
from datetime import datetime, timedelta

def export_validated_feedback(days=7):
    """Export human-validated annotations from Argilla."""
    rg.init(api_url="http://localhost:6900", api_key="your-api-key")

    dataset = rg.load("pii-review-queue")

    # Get records validated in the last N days
    validated = []
    for record in dataset.records:
        if record.status == "validated":
            validated.append({
                "text": record.fields["text"],
                "entities": record.responses[0].values["pii_entities"]
            })

    return validated

def generate_synthetic_variations(validated_data, num_variations=5):
    """Generate synthetic variations of corrected examples."""
    from gliner_finetune import generate

    synthetic = []
    for item in validated_data:
        variations = generate(
            examples=[item],
            entity_types=list(set(e["label"] for e in item["entities"])),
            num_variations=num_variations
        )
        synthetic.extend(variations)

    return synthetic

def convert_to_gliner_format(data):
    """Convert to GLiNER training format."""
    gliner_data = []
    for item in data:
        tokens = item["text"].split()
        ner = []
        for entity in item["entities"]:
            # Convert character spans to token indices
            start_char = entity["start"]
            end_char = entity["end"]

            start_token = len(item["text"][:start_char].split())
            end_token = len(item["text"][:end_char].split()) - 1

            ner.append([start_token, end_token, entity["label"]])

        gliner_data.append({
            "tokenized_text": tokens,
            "ner": ner
        })

    return gliner_data

def retrain_model():
    """Main retraining pipeline."""
    print(f"[{datetime.now()}] Starting retraining pipeline...")

    # 1. Export validated feedback
    print("Exporting validated feedback...")
    validated_data = export_validated_feedback(days=7)
    print(f"  Found {len(validated_data)} validated samples")

    if len(validated_data) < 10:
        print("  Not enough new data for retraining. Skipping.")
        return

    # 2. Generate synthetic variations
    print("Generating synthetic variations...")
    synthetic_data = generate_synthetic_variations(validated_data)
    print(f"  Generated {len(synthetic_data)} synthetic samples")

    # 3. Load original training data
    print("Loading original training data...")
    with open("data/original_train.json", "r") as f:
        original_data = json.load(f)

    # 4. Combine datasets
    combined_data = original_data + convert_to_gliner_format(validated_data + synthetic_data)
    print(f"  Total training samples: {len(combined_data)}")

    # 5. Fine-tune model
    print("Fine-tuning model...")
    model = GLiNER.from_pretrained("knowledgator/gliner-pii-base-v1.0")

    training_args = TrainingArguments(
        output_dir="models/pii-shield-updated",
        num_train_epochs=3,
        per_device_train_batch_size=8,
        learning_rate=1e-5,
        warmup_ratio=0.1,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=combined_data
    )

    trainer.train()

    # 6. Evaluate new model
    print("Evaluating new model...")
    with open("data/test.json", "r") as f:
        test_data = json.load(f)

    new_f1 = evaluate_model(model, test_data)
    current_f1 = get_current_model_f1()

    print(f"  Current model F1: {current_f1:.4f}")
    print(f"  New model F1: {new_f1:.4f}")

    # 7. Deploy if improved
    if new_f1 > current_f1:
        print("New model is better! Deploying...")
        model.save_pretrained("models/pii-shield-production")
        update_model_config("models/pii-shield-production")
        print("Deployment complete.")
    else:
        print("New model did not improve. Keeping current model.")

    print(f"[{datetime.now()}] Retraining pipeline complete.")

if __name__ == "__main__":
    retrain_model()
```

### Component 5: Cron Job Setup

```bash
# /etc/cron.d/pii-shield-retrain

# Run retraining every Sunday at 2 AM
0 2 * * 0 /path/to/venv/bin/python /path/to/scripts/retrain_model.py >> /var/log/pii-retrain.log 2>&1
```

---

## Implementation Roadmap

### Phase 1: Quick Wins (Week 1)
- [ ] Switch to `knowledgator/gliner-pii-base-v1.0` (+5% F1)
- [ ] Add feedback button to Chrome extension UI
- [ ] Create `/api/feedback` endpoint
- [ ] Store corrections in `feedback_data.jsonl`

### Phase 2: Human-in-the-Loop (Week 2-3)
- [ ] Set up Argilla server (Docker or cloud)
- [ ] Create review dataset with PII labels
- [ ] Route low-confidence detections to review queue
- [ ] Build simple review dashboard

### Phase 3: Continuous Learning (Week 4-6)
- [ ] Implement `retrain_model.py` script
- [ ] Set up synthetic data generation with GPT
- [ ] Create evaluation pipeline
- [ ] Configure weekly cron job
- [ ] A/B test deployment process

### Phase 4: Advanced Features (Future)
- [ ] Online learning for real-time adaptation
- [ ] Active learning acquisition functions
- [ ] Multi-model ensemble
- [ ] Domain-specific fine-tuning (medical, financial, etc.)

---

## Resources & Sources

### Models
- [urchade/gliner_multi_pii-v1](https://huggingface.co/urchade/gliner_multi_pii-v1) - Current model
- [knowledgator/gliner-pii-base-v1.0](https://huggingface.co/knowledgator/gliner-pii-base-v1.0) - Recommended upgrade
- [nvidia/gliner-PII](https://huggingface.co/nvidia/gliner-PII) - Enterprise option
- [gretelai/gretel-gliner-bi-large-v1.0](https://huggingface.co/gretelai/gretel-gliner-bi-large-v1.0) - Highest accuracy

### Datasets
- [nvidia/nemotron-pii](https://huggingface.co/datasets/nvidia/nemotron-pii) - 200k synthetic PII records
- [gretelai/gretel-pii-masking-en-v1](https://huggingface.co/datasets/gretelai/gretel-pii-masking-en-v1) - 60k PII records

### Tools & Libraries
- [GLiNER GitHub](https://github.com/urchade/GLiNER) - Official repository
- [gliner-finetune](https://github.com/wjbmattingly/gliner-finetune) - Synthetic data + fine-tuning
- [Argilla](https://github.com/argilla-io/argilla) - Human-in-the-loop annotation

### Tutorials
- [Fine-Tuning GLiNER with Label Studio](https://labelstud.io/blog/fine-tuning-generalist-models-for-named-entity-recognition/)
- [Argilla Token Classification](https://docs.argilla.io/v2.0/tutorials/token_classification/)
- [Zero-Shot NER Fine-Tuning](https://github.com/chrishokamp/zero-shot-ner-fine-tuning)

### Research
- [GLiNER Paper (NAACL 2024)](https://arxiv.org/abs/2311.08526)
- [Hybrid PII Detection in Financial Documents](https://www.nature.com/articles/s41598-025-04971-9)
- [Human-in-the-Loop Active Learning](https://humansintheloop.org/how-do-you-build-human-in-the-loop-ai-pipelines-using-active-learning/)

---

## Quick Reference

### Model Switch (One-Line Change)
```python
# config.py
DEFAULT_MODEL = "knowledgator/gliner-pii-base-v1.0"  # was: urchade/gliner_multi_pii-v1
```

### Check Model Performance
```python
from gliner import GLiNER

model = GLiNER.from_pretrained("knowledgator/gliner-pii-base-v1.0")
entities = model.predict_entities(
    "Contact John at john@example.com or 555-123-4567",
    labels=["person", "email", "phone"],
    threshold=0.3
)
print(entities)
```

### Start Argilla (Docker)
```bash
docker run -d --name argilla \
  -p 6900:6900 \
  -e ARGILLA_ELASTICSEARCH=http://elasticsearch:9200 \
  argilla/argilla-server:latest
```
