# Documentation guide

Read these documents in order if you are new to the project.

| Document | Question it answers |
| --- | --- |
| [Product brief](product-brief.md) | What problem are we solving, for whom, and why? |
| [SRS PDF](requirements/wireless-assistant-srs.pdf) / [editable SRS](requirements/wireless-assistant-srs.md) | What must the assistant do, and how will it be checked? |
| [Architecture](architecture.md) | How do A, B, C and backend control work together? |
| [Decision register](decisions.md) | What is agreed, what is proposed, and what is still open? |
| [Roadmap](roadmap.md) | What should be done next, and when is each stage complete? |
| [Requirements build guide](requirements/README.md) | How is the PDF rebuilt and kept consistent with its source? |
| [Contribution guide](../CONTRIBUTING.md) | How should changes be proposed, checked and recorded? |
| [Changelog](../CHANGELOG.md) | What changed in the published documentation? |

## Reading and status rules

The product brief preserves the five agreed user problems. The SRS is the detailed behavior reference. The architecture and roadmap summarize it; they do not silently add requirements or select technologies.

SRS labels distinguish CONFIRMED behavior from PROPOSED implementation requirements. The decision register tracks unresolved settings and the approval work. Neither a merged document nor a check mark in a documentation task is evidence that application behavior has been implemented.

Current baseline: **SRS v0.9.1, review draft**. Requirements documentation is complete; baseline approval and implementation are still pending.

## Keeping the documents consistent

For a change to behavior, review the product brief, affected SRS requirement IDs, acceptance scenarios and decision entries together. Rebuild the PDF when the SRS source or renderer changes. Update the roadmap only when the stage or its exit condition changes.
