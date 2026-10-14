# Dataset attribution

The excerpts in `corpus.jsonl`, original questions/answers/supporting facts in
`gold.jsonl`, and adapted summary/withheld-evidence tasks derive from **HotpotQA**:
Yang, Qi, Zhang, et al. (2018), *HotpotQA: A Dataset for Diverse, Explainable
Multi-hop Question Answering*, EMNLP.

- Project: https://hotpotqa.github.io/
- Official dataset mirror: https://huggingface.co/datasets/hotpotqa/hotpot_qa
- License: **Creative Commons Attribution-ShareAlike 4.0 International**
  https://creativecommons.org/licenses/by-sa/4.0/
- Source revision and file checksum: `manifest.json`.
- Original Wikipedia article titles and attribution links: each corpus document.

Changes: deterministic subset selection, pooled distractor corpus, stable sentence
identifiers, summary task derivation, and controlled supporting-article removal.
These dataset adaptations remain CC BY-SA 4.0. The repository's MIT license applies
to original software, not these data files. Wikipedia links are attribution links
to live pages; the checked-in snapshot is the actual evaluation evidence.
