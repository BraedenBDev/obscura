# Generative AI Declaration

Obscura was built with the assistance of generative AI tools at various stages of development. In the interest of transparency, we disclose the tools used below.

## AI-Assisted Development Tools

### Claude Code (Anthropic) — Opus 4.6
Used for code architecture, refactoring, testing infrastructure, code review, and open-source packaging. Claude Code served as a development partner throughout the project for planning, debugging, and implementation.

### ChatGPT Codex (OpenAI)
Used for initial code generation, prototyping, and exploratory development during early project phases.

### Lovable
Used for UI/UX design exploration and rapid prototyping of interface components.

## AI Models in Production

### GLiNER — Named Entity Recognition

Obscura uses [GLiNER](https://github.com/urchade/GLiNER) (Generalist and Lightweight Model for Named Entity Recognition) for real-time PII detection. GLiNER is a compact NER model that identifies entities using natural language descriptions rather than fixed label sets.

**Models used:**

| Model | Source | Purpose | License |
|-------|--------|---------|---------|
| [`urchade/gliner_multi_pii-v1`](https://huggingface.co/urchade/gliner_multi_pii-v1) | Hugging Face | Primary PII detection (PII-specific fine-tune) | Apache 2.0 |
| [`urchade/gliner_small-v2.1`](https://huggingface.co/urchade/gliner_small-v2.1) | Hugging Face | Fallback general-purpose NER | Apache 2.0 |

**Citation:**

```bibtex
@misc{zaratiana2023gliner,
    title={GLiNER: Generalist Model for Named Entity Recognition using Bidirectional Transformer},
    author={Urchade Zaratiana and Nadi Tomeh and Pierre Holat and Thierry Charnois},
    year={2023},
    eprint={2311.08526},
    archivePrefix={arXiv},
    primaryClass={cs.CL}
}
```

The GLiNER models are downloaded from [Hugging Face Hub](https://huggingface.co) on first run and are not bundled with the source code. Model files are excluded from version control via `.gitignore`.

## Human Oversight

All AI-generated code was reviewed, tested, and validated by the human authors. The architectural decisions, security considerations, and final implementation choices were made by the development team. AI tools were used as accelerators, not replacements for engineering judgment.

## Co-Authors

- **Braeden** — [github.com/BraedenBDev](https://github.com/BraedenBDev)
- **Vivek Chiliveri** — [github.com/vivekchiliveri](https://github.com/vivekchiliveri)
- **Claude Code (Opus 4.6)** — AI development partner
