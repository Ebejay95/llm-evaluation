# Problem Statement: Security Advisory Assistant Evaluation

## Overview

This project develops a domain-specific evaluation for an AI assistant in the field of cybersecurity consulting. The assistant is designed to help SME decision-makers with structured risk assessment and control selection based on established frameworks and best practices.

## Target Users

**Primary users:**
- Chief Information Security Officers (CISOs) in EU SMEs (50-500 employees)
- OT/IT managers in manufacturing companies
- Compliance officers with limited security resources

**Context of use:**
- Time pressure due to compliance requirements (NIS2, ISO 27001)
- Limited internal security expertise
- Need for comprehensible, framework-based recommendations

## Core tasks of the AI assistant

### 1. Risk scenario identification
**What the assistant should do:**
- Suggest the 3-5 most critical risk scenarios based on the company profile (industry, size, OT share, compliance status)
- Provide a structured rationale for each scenario (“Why is this relevant to you?”)
- Include references to established threat frameworks (MITRE ATT&CK, NIST CSF)

**Example input:** “Medium-sized machine manufacturer, 200 employees, mixed IT/OT environment, subject to NIS2”

**Expected output:**

```
Top risks for your profile:
1. Ransomware via OT-IT bridges (Why: Critical production + limited OT segmentation)
2. Supply chain attacks (Why: Dependence on suppliers + limited vendor assessments)
3. [...]
```

### 2. Control recommendations with framework mapping
**What the assistant should do:**
- Suggest appropriate, implementable controls for identified risks
- Cluster controls according to priority/effort (“quick wins,” “strategic measures”)
- Provide mapping to relevant standards (ISO 27001, NIST CSF, BSI basic protection)
- Provide realistic implementation guidance for SME context

### 3. Generate structured follow-up questions
**What the Assistant should do:**
- Targeted questions to deepen the risk analysis
- Evidence-based questions (“Have you already...?”, “How often do you check...?”)
- Coverage assessment (“Which OT zones are affected?”)
- Prioritization aids (“Budget/time frame for implementation?”)

## Limitations (out of scope)

**What the assistant should NOT do:**
- Calculate automatic risk scores without human validation
- Make specific vendor recommendations
- Create detailed technical implementation instructions
- Legally assess compliance status
- Perform pen-test-like concrete vulnerability assessments

**Technical limitations:**
- No integration of external APIs (threat intelligence feeds)
- No automatic calibration of scoring models
- Restriction to static JSON knowledge base

## Data sources (source of truth)

**Structured knowledge base:**
- `company_profiles.json`: Industry templates with typical risk patterns
- `library_scenarios.json`: Catalog of proven risk scenarios with framework mapping
- `library_controls.json`: Control measures library with implementation notes
- `framework_mappings.json`: References to ISO 27001, NIST CSF, BSI GS

**Evaluation Data Set:**
- Realistic company profiles as test cases
- Manually validated “golden standard” recommendations
- Edge cases and typical misconfigurations

## Success Criteria (Qualitative)

### Correctness
- **No hallucinations**: All recommendations must be anchored in the JSON KB
- **Framework consistency**: References to standards must be correct
- **Industry relevance**: Proposed scenarios must match the company profile

### Explainability
- **Comprehensible justifications**: Each recommendation must include a “why” component
- **Transparent sources**: Clear referencing of the framework elements used
- **Structured argumentation**: Logical chain of profile → risk → control

### Consistency
- **Reproducible results**: Identical inputs lead to comparable outputs
- **Uniform level of detail**: Balanced depth for all recommendations
- **Coherent terminology**: Consistent use of technical terms

### Practicality
- **SME focus**: Recommendations must be feasible with limited resources
- **Prioritization aid**: Clear distinction between “must-have” and “nice-to-have”
- **Action orientation**: Concrete next steps instead of abstract theory

## Evaluation metrics (Proposal)

### Custom Metrics
- **Framework Accuracy**: Proportion of correct standard references
- **Relevance Score**: Evaluation of scenario fit by domain experts
- **Explainability Index**: Quality of explanations (manually annotated)
- **Hallucination Detection**: Proportion of non-KB-based claims

### Standard Metrics
- **Semantic Similarity**: Comparison with gold standard recommendations
- **Coverage**: Proportion of relevant risk categories covered
- **Consistency**: Variance in repeated evaluations of the same inputs

## Failure Modes (Expected Challenges)

1. **Over-Generic Advice**: Recommendations that are too general and lack SME/industry specifics
2. **Framework Mixing**: Inconsistent mixing of different standards
3. **Compliance Overclaim**: Overinterpretation of control effectiveness
4. **Complexity mismatch**: Solutions that are too complex for the SME context
5. **Outdated references**: References to outdated framework versions