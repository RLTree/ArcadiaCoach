"""Foundation-aware curriculum augmentation for ambitious or struggling learners."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .assessment_result import AssessmentGradingResult
from .learner_profile import (
    CurriculumModule,
    CurriculumPlan,
    EloCategoryDefinition,
    EloRubricBand,
    FoundationModuleReference,
    FoundationTrack,
    GoalParserInference,
)


@dataclass(frozen=True)
class _ModuleTemplate:
    module_id: str
    title: str
    summary: str
    objectives: Tuple[str, ...]
    activities: Tuple[str, ...]
    deliverables: Tuple[str, ...]
    estimated_minutes: int
    tier: int = 1


@dataclass(frozen=True)
class _CategoryTemplate:
    key: str
    label: str
    description: str
    focus_areas: Tuple[str, ...]
    weight: float
    rubric: Tuple[Tuple[str, str], ...]
    success_criteria: Tuple[str, ...]
    modules: Tuple[_ModuleTemplate, ...]


_FOUNDATION_LIBRARY: Dict[str, _CategoryTemplate] = {
    "python-foundations": _CategoryTemplate(
        key="python-foundations",
        label="Python Foundations",
        description="Core Python syntax, control flow, and functions for productive scripting.",
        focus_areas=("syntax", "control-flow", "functions"),
        weight=1.25,
        rubric=(
            ("Exploring", "Needs guidance to write and debug basic Python scripts."),
            ("Developing", "Can compose functions and modules with limited support."),
            ("Proficient", "Builds maintainable Python components with style guides and tests."),
        ),
        success_criteria=(
            "Ship a daily Python practice log covering syntax, functions, and modules.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-python-syntax",
                title="Python Syntax & Control Flow Reset",
                summary="Rebuild core Python constructs from variables to iteration with deliberate practice.",
                objectives=(
                    "Write idiomatic Python that avoids code smells highlighted during the assessment.",
                    "Use control flow (loops, conditionals, pattern matching) to make scripts resilient.",
                    "Adopt linting and formatting tools to reinforce muscle memory.",
                ),
                activities=(
                    "Complete REPL kata covering variables, branching, and iteration.",
                    "Refactor assessment responses into clean, commented scripts.",
                ),
                deliverables=(
                    "Publish a short practice journal that documents three syntax wins and two remaining questions.",
                ),
                estimated_minutes=180,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-python-structuring",
                title="Functions, Modules, and Packaging",
                summary="Turn throwaway scripts into reusable, well-structured Python packages.",
                objectives=(
                    "Design functions with single responsibility and clear typing.",
                    "Organise projects with virtual environments, requirements management, and packaging basics.",
                    "Document behaviour with docstrings and lightweight READMEs.",
                ),
                activities=(
                    "Create a mini utilities package with CLI entry points.",
                    "Instrument scripts with logging and type hints based on assessment gaps.",
                ),
                deliverables=(
                    "Submit a `utilities` package with README, pyproject metadata, and usage examples.",
                ),
                estimated_minutes=210,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-python-testing",
                title="Testing, Errors, and Tooling",
                summary="Adopt professional Python tooling for quality and iteration speed.",
                objectives=(
                    "Write pytest suites that cover edge cases surfaced during onboarding.",
                    "Handle exceptions gracefully and log actionable context.",
                    "Automate formatting, linting, and tests with pre-commit or task runners.",
                ),
                activities=(
                    "Backfill tests for assessment code using pytest parametrisation.",
                    "Set up ruff, black, and pre-commit hooks to enforce standards automatically.",
                ),
                deliverables=(
                    "Deliver a demo repository with passing tests, linting, and CI-ready configuration.",
                ),
                tier=2,
                estimated_minutes=240,
            ),
        ),
    ),
    "data-manipulation": _CategoryTemplate(
        key="data-manipulation",
        label="Data Manipulation & Analysis",
        description="Build fluency with NumPy, pandas, and exploratory analysis workflows.",
        focus_areas=("numpy", "pandas", "eda"),
        weight=1.15,
        rubric=(
            ("Exploring", "Relies on ad-hoc scripts to inspect data."),
            ("Developing", "Uses NumPy and pandas but needs guidance to optimise pipelines."),
            ("Proficient", "Designs reusable notebooks and datasets with clear documentation."),
        ),
        success_criteria=(
            "Deliver a reproducible exploratory analysis that informs next-step experiments.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-numpy-basics",
                title="NumPy Fundamentals & Vector Thinking",
                summary="Master array operations, broadcasting, and performance-aware data pipelines.",
                objectives=(
                    "Translate loop-heavy scripts into vectorised NumPy operations.",
                    "Use dtypes, slicing, and reshaping to prepare model-ready arrays.",
                    "Profile code paths to spot memory and performance bottlenecks.",
                ),
                activities=(
                    "Rewrite assessment exercises with NumPy arrays and benchmarks.",
                    "Complete vectorisation drills targeting goal-specific datasets.",
                ),
                deliverables=("Share a notebook comparing naive vs vectorised solutions with timing data.",),
                estimated_minutes=210,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-pandas-proficiency",
                title="Pandas DataFrames in Practice",
                summary="Develop rigorous data munging, validation, and summarisation habits with pandas.",
                objectives=(
                    "Load, clean, and merge messy datasets using idiomatic pandas patterns.",
                    "Validate data with schema checks and assertive testing.",
                    "Communicate insights with tidy tables, plots, and narrative takeaways.",
                ),
                activities=(
                    "Refactor onboarding datasets with method-chaining pipelines.",
                    "Instrument notebooks with `pandera` or custom validators to prevent regressions.",
                ),
                deliverables=("Produce a polished exploratory notebook with decisions and follow-up questions.",),
                estimated_minutes=240,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-data-tooling",
                title="Data Tooling & Reproducibility",
                summary="Stand up dependable analysis environments using notebooks, scripts, and tracking.",
                objectives=(
                    "Adopt project structures that separate ETL, exploration, and reporting.",
                    "Version datasets and notebooks for collaborative review.",
                    "Automate common analytics tasks with Makefiles or invoke.",
                ),
                activities=(
                    "Create a cookiecutter-style analytics project template tied to the learner's goal.",
                    "Integrate lightweight experiment tracking (Weights & Biases, MLflow, or custom logs).",
                ),
                deliverables=("Submit a reproducible analysis repo with bootstrap instructions and sample runs.",),
                estimated_minutes=270,
                tier=2,
            ),
        ),
    ),
    "math-statistics": _CategoryTemplate(
        key="math-statistics",
        label="Math & Statistical Foundations",
        description="Reinforce the mathematical intuition needed for advanced analytics and machine learning.",
        focus_areas=("probability", "linear-algebra", "statistics"),
        weight=1.05,
        rubric=(
            ("Exploring", "Struggles to connect math concepts to implementation."),
            ("Developing", "Applies statistical tools with partial confidence."),
            ("Proficient", "Explains and implements statistical techniques with clarity."),
        ),
        success_criteria=(
            "Complete spaced-practice drills that tie math concepts directly to the long-term goal.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-probability-statistics",
                title="Probability & Statistics Refresh",
                summary="Reconnect descriptive statistics, probability distributions, and inference to coding practice.",
                objectives=(
                    "Interpret variance, covariance, and uncertainty in goal-aligned datasets.",
                    "Select appropriate statistical tests and explain trade-offs.",
                    "Visualise uncertainty and communicate conclusions responsibly.",
                ),
                activities=(
                    "Solve bite-sized inference problems in a spaced repetition deck.",
                    "Annotate notebook outputs with narrative explanations tailored to stakeholders.",
                ),
                deliverables=("Compile a playbook summarising when to use each statistical technique encountered.",),
                estimated_minutes=180,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-linear-algebra",
                title="Linear Algebra for Practitioners",
                summary="Make matrix operations and vector spaces intuitive through code-first exploration.",
                objectives=(
                    "Implement matrix factorisation, eigen decomposition, and tensor basics in NumPy.",
                    "Explain how linear algebra underpins model training for the learner's ambitions.",
                    "Use visual and code demonstrations to teach the concept back to future learners.",
                ),
                activities=(
                    "Recreate core linear algebra routines from scratch, validating against NumPy.",
                    "Document insights in sketchnotes or narrated Loom videos for spaced review.",
                ),
                deliverables=("Deliver a notebook linking each linear algebra tool to a practical ML scenario.",),
                estimated_minutes=240,
                tier=2,
            ),
        ),
    ),
    "machine-learning": _CategoryTemplate(
        key="machine-learning",
        label="Machine Learning Foundations",
        description="Lay the groundwork for building, evaluating, and deploying ML systems.",
        focus_areas=("modeling-basics", "evaluation", "deployment"),
        weight=1.2,
        rubric=(
            ("Exploring", "Experiments with models without clear evaluation."),
            ("Developing", "Trains baseline models and compares metrics with guidance."),
            ("Proficient", "Designs experiments, evaluates rigorously, and structures iteration plans."),
        ),
        success_criteria=(
            "Ship an end-to-end ML experiment log with baselines, metrics, and next steps.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-ml-baselines",
                title="Designing Baselines & Feature Pipelines",
                summary="Frame problems, craft datasets, and train interpretable baseline models.",
                objectives=(
                    "Translate the learner's ultimate goal into a supervised learning framing.",
                    "Engineer baseline features and document assumptions up front.",
                    "Stand up evaluation harnesses that measure the right signals.",
                ),
                activities=(
                    "Build logistic/linear baselines and compare against naive heuristics.",
                    "Draft an experimentation rubric emphasising interpretability and ethics.",
                ),
                deliverables=("Log experiment baselines with feature notes and a reproducibility checklist.",),
                estimated_minutes=270,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-ml-iteration",
                title="Evaluation, Error Analysis, & Iteration Plans",
                summary="Level up model diagnostics and deployment-readiness thinking.",
                objectives=(
                    "Interpret learning curves, confusion matrices, and regression diagnostics.",
                    "Design error analysis rituals that surface bias and reliability concerns.",
                    "Draft deployment guardrails tailored to the learner's target environment.",
                ),
                activities=(
                    "Create a decision log summarising experiment outcomes and open risks.",
                    "Prototype a deployment checklist covering monitoring, rollback, and alerts.",
                ),
                deliverables=("Publish an iteration roadmap linking evaluation findings to next experiments.",),
                estimated_minutes=240,
                tier=2,
            ),
            _ModuleTemplate(
                module_id="foundation-ml-systems",
                title="Production ML Systems & Observability",
                summary="Bridge models into resilient production services with observability baked in.",
                objectives=(
                    "Plan model packaging, dependency management, and API or batch deployment paths.",
                    "Instrument model monitoring (data drift, performance drift, cost) from day one.",
                    "Collaborate with stakeholders to define success metrics and rollback triggers.",
                ),
                activities=(
                    "Design a system architecture diagram and runbook for the target product.",
                    "Simulate drift scenarios and outline mitigation playbooks.",
                ),
                deliverables=("Deliver a production readiness brief with architecture, monitoring, and support plan.",),
                estimated_minutes=300,
                tier=3,
            ),
        ),
    ),
    "software-practices": _CategoryTemplate(
        key="software-practices",
        label="Software Engineering Habits",
        description="Strengthen version control, code review, and automation muscles that support long projects.",
        focus_areas=("git", "testing", "automation"),
        weight=1.0,
        rubric=(
            ("Exploring", "Commits code without structure or review."),
            ("Developing", "Uses git and testing inconsistently."),
            ("Proficient", "Automates quality gates and collaborates with confident workflows."),
        ),
        success_criteria=(
            "Adopt a repeatable workflow for branching, testing, and delivering incremental value.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-git-workflows",
                title="Git Workflows & Collaboration",
                summary="Move from ad-hoc commits to disciplined, review-friendly branching strategies.",
                objectives=(
                    "Practice topic branches, semantic commits, and pull request hygiene.",
                    "Use code review checklists that reinforce maintainability and accessibility.",
                    "Integrate issue trackers to connect work units to goals.",
                ),
                activities=(
                    "Recreate assessment solutions using feature branches and annotated PRs.",
                    "Pair on review simulations that emphasise feedback loops.",
                ),
                deliverables=("Submit a branch management guide tailored to the learner's collaboration context.",),
                estimated_minutes=180,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-ci-automation",
                title="Continuous Integration & Developer Automation",
                summary="Automate linting, testing, and deployment previews to sustain velocity.",
                objectives=(
                    "Configure CI pipelines (GitHub Actions or equivalent) triggered by pull requests.",
                    "Instrument quality gates tied to metrics from the onboarding assessment gaps.",
                    "Adopt task runners (Make, Invoke, Nox) for reliable local automation.",
                ),
                activities=(
                    "Publish a CI pipeline that runs tests, linters, and reports coverage.",
                    "Automate release notes or changelog updates to reinforce reflection.",
                ),
                deliverables=("Deliver a continuous integration pipeline with documentation and troubleshooting steps.",),
                estimated_minutes=210,
                tier=2,
            ),
        ),
    ),
    "project-delivery": _CategoryTemplate(
        key="project-delivery",
        label="Project Delivery & Reflection",
        description="Plan multi-month work, measure progress, and communicate learning transparently.",
        focus_areas=("roadmapping", "communication", "reflection"),
        weight=0.9,
        rubric=(
            ("Exploring", "Struggles to plan and reflect on progress."),
            ("Developing", "Creates plans but needs accountability to adapt them."),
            ("Proficient", "Maintains roadmaps, communicates blockers, and iterates autonomously."),
        ),
        success_criteria=(
            "Maintain a living roadmap, weekly reflection cadence, and evidence of milestone completion.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-roadmapping",
                title="Strategic Roadmaps & Milestones",
                summary="Translate ambitious goals into phased, measurable delivery plans.",
                objectives=(
                    "Define milestone outcomes, success metrics, and dependency diagrams.",
                    "Balance foundational work with stretch experiments across months.",
                    "Create accountability systems that respect AuDHD energy rhythms.",
                ),
                activities=(
                    "Draft a 6-12 month roadmap with quarterly objectives and weekly themes.",
                    "Establish progress dashboards and reflection prompts aligned to accessibility needs.",
                ),
                deliverables=("Publish a roadmap and milestone brief ready for coach review.",),
                estimated_minutes=180,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-reflection",
                title="Reflection, Knowledge Capture, & Momentum",
                summary="Build reflection rituals that solidify learning and surface blockers early.",
                objectives=(
                    "Adopt daily or weekly reflection prompts tied to the learner's goal.",
                    "Capture decisions, assumptions, and open risks in a lightweight knowledge base.",
                    "Measure momentum using leading indicators, not just outputs.",
                ),
                activities=(
                    "Pilot multiple reflection formats (audio, written, mind maps) to find a sustainable fit.",
                    "Create a personal user manual that documents working preferences and support needs.",
                ),
                deliverables=("Share a reflection cadence template and first week's entries.",),
                estimated_minutes=150,
                tier=1,
            ),
            _ModuleTemplate(
                module_id="foundation-stakeholder-updates",
                title="Communicating Progress & Impact",
                summary="Craft concise updates and demos that keep stakeholders engaged.",
                objectives=(
                    "Summarise technical progress and learning with clarity for non-technical audiences.",
                    "Leverage demos, Loom walkthroughs, and visual dashboards to showcase outcomes.",
                    "Capture feedback loops that inform the next iteration of the roadmap.",
                ),
                activities=(
                    "Create a milestone update template with visuals and key metrics.",
                    "Record a dry-run demo and self-critique for clarity and pacing.",
                ),
                deliverables=("Deliver a milestone update package (deck or Loom) ready to share with mentors.",),
                estimated_minutes=165,
                tier=2,
            ),
        ),
    ),
    "software-architecture": _CategoryTemplate(
        key="software-architecture",
        label="Systems & Architecture Foundations",
        description="Ensure solid understanding of backend patterns, APIs, and deployment basics.",
        focus_areas=("architecture", "apis", "scalability"),
        weight=1.1,
        rubric=(
            ("Exploring", "Implements features without broader architectural awareness."),
            ("Developing", "Designs services with guidance on scalability and reliability."),
            ("Proficient", "Ships services with resilience, observability, and clear contracts."),
        ),
        success_criteria=(
            "Design and document service architectures that scale with the learner's ambitions.",
        ),
        modules=(
            _ModuleTemplate(
                module_id="foundation-api-design",
                title="API & Service Design Essentials",
                summary="Model resources, contracts, and versioning strategies that support long-term evolution.",
                objectives=(
                    "Design RESTful and event-driven APIs with consistent contracts.",
                    "Document services with OpenAPI or gRPC schemas and consumer-driven tests.",
                    "Plan authentication, authorisation, and rate limiting for real users.",
                ),
                activities=(
                    "Model the learner's target product with resource and domain diagrams.",
                    "Prototype a service contract and backwards compatibility strategy.",
                ),
                deliverables=("Submit an API design doc with schemas, error handling, and rollout plan.",),
                estimated_minutes=210,
                tier=2,
            ),
            _ModuleTemplate(
                module_id="foundation-observability",
                title="Observability, Scaling, & Reliability",
                summary="Plan monitoring, alerting, and scaling strategies before launch.",
                objectives=(
                    "Instrument services with logs, metrics, and traces aligned to SLOs.",
                    "Evaluate scaling options (containers, serverless, queues) for load patterns.",
                    "Draft incident runbooks that respect access needs and response protocols.",
                ),
                activities=(
                    "Design an observability dashboard for the learner's future service.",
                    "Simulate incident scenarios and articulate mitigation strategies.",
                ),
                deliverables=("Deliver an observability and scaling playbook with diagrams and response steps.",),
                estimated_minutes=240,
                tier=3,
            ),
        ),
    ),
}

_MODULE_TEMPLATE_INDEX: Dict[str, Tuple[str, _ModuleTemplate]] = {}
for _category in _FOUNDATION_LIBRARY.values():
    for _module in _category.modules:
        _MODULE_TEMPLATE_INDEX[_module.module_id] = (_category.key, _module)


def _add_module_from_template(
    plan: CurriculumPlan,
    module_template: _ModuleTemplate,
    category_key: str,
    existing_ids: Set[str],
) -> None:
    if module_template.module_id in existing_ids:
        return
    plan.modules.append(
        CurriculumModule(
            module_id=module_template.module_id,
            category_key=category_key,
            title=module_template.title,
            summary=module_template.summary,
            objectives=list(module_template.objectives),
            activities=list(module_template.activities),
            deliverables=list(module_template.deliverables),
            estimated_minutes=module_template.estimated_minutes,
        )
    )
    existing_ids.add(module_template.module_id)


def _find_track_for_category(
    inference: Optional[GoalParserInference],
    category_key: str,
) -> Optional[FoundationTrack]:
    if inference is None:
        return None
    for track in inference.tracks:
        if track.track_id == category_key:
            return track
        for reference in track.recommended_modules:
            if reference.category_key == category_key:
                return track
    return None


def _synthesise_rubric(label: str) -> List[EloRubricBand]:
    return [
        EloRubricBand(level="Exploring", descriptor=f"Beginning {label} fundamentals."),
        EloRubricBand(level="Developing", descriptor=f"Applies {label} skills with guided support."),
        EloRubricBand(level="Proficient", descriptor=f"Independently delivers {label} outcomes."),
    ]


_BASE_FOUNDATION_KEYS: Tuple[str, ...] = (
    "python-foundations",
    "software-practices",
    "project-delivery",
)

_DATA_FOUNDATION_KEYS: Tuple[str, ...] = (
    "data-manipulation",
    "math-statistics",
    "machine-learning",
)

_BACKEND_FOUNDATION_KEYS: Tuple[str, ...] = (
    "software-architecture",
)


def _normalise_goal(goal: str) -> str:
    text = goal.lower()
    return re.sub(r"\s+", " ", text.strip())


def _average_score(result: Optional[AssessmentGradingResult]) -> Optional[float]:
    if result is None:
        return None
    scores: List[float] = []
    if result.category_outcomes:
        for outcome in result.category_outcomes:
            scores.append(outcome.average_score)
    if not scores and result.task_results:
        scores = [task.score for task in result.task_results]
    return mean(scores) if scores else None


def _determine_foundation_keys(
    goal: str,
    average_score: Optional[float],
    existing_categories: Iterable[str],
    module_count: int,
) -> List[str]:
    normalized_goal = _normalise_goal(goal)
    desired: List[str] = []
    if module_count < 10 or not existing_categories:
        desired.extend(_BASE_FOUNDATION_KEYS)
    else:
        desired.extend(k for k in _BASE_FOUNDATION_KEYS if k not in existing_categories)

    if any(keyword in normalized_goal for keyword in ("data", "analytics", "analysis", "insight", "dataset", "science")):
        desired.extend(_DATA_FOUNDATION_KEYS)
    if any(keyword in normalized_goal for keyword in ("machine learning", "ml", "ai", "artificial intelligence", "model")):
        desired.extend(_DATA_FOUNDATION_KEYS)
    if any(keyword in normalized_goal for keyword in ("backend", "api", "platform", "service", "infrastructure")):
        desired.extend(_BACKEND_FOUNDATION_KEYS)

    if average_score is not None:
        if average_score < 0.65:
            desired.extend(_BASE_FOUNDATION_KEYS)
            desired.extend(_DATA_FOUNDATION_KEYS)
        if average_score < 0.45:
            desired.extend(_FOUNDATION_LIBRARY.keys())

    # Preserve order while removing duplicates.
    seen: set[str] = set(existing_categories)
    ordered: List[str] = []
    for key in desired:
        if key not in seen and key in _FOUNDATION_LIBRARY:
            ordered.append(key)
            seen.add(key)
    return ordered


def _tier_limit(average_score: Optional[float]) -> int:
    if average_score is None:
        return 1
    if average_score < 0.35:
        return 3
    if average_score < 0.6:
        return 2
    return 1


def ensure_foundational_curriculum(
    *,
    goal: str,
    plan: CurriculumPlan,
    categories: Sequence[EloCategoryDefinition],
    assessment_result: Optional[AssessmentGradingResult] = None,
    goal_inference: Optional[GoalParserInference] = None,
) -> Tuple[List[EloCategoryDefinition], CurriculumPlan]:
    """Augment the curriculum and ELO categories with foundational coverage."""

    plan_copy = plan.model_copy(deep=True)
    category_list = [entry.model_copy(deep=True) for entry in categories]
    existing_category_keys: Set[str] = {category.key for category in category_list}
    existing_module_ids: Set[str] = {module.module_id for module in plan_copy.modules}

    track_weights: Dict[str, float] = {}
    track_modules: Dict[str, List[Tuple[FoundationTrack, FoundationModuleReference]]] = {}
    track_notes: List[str] = []
    desired_keys: List[str] = []
    if goal_inference:
        for track in goal_inference.tracks:
            if track.notes:
                note = track.notes.strip()
                if note:
                    track_notes.append(note)
            weight = track.weight if track.weight and track.weight > 0 else 1.0
            for reference in track.recommended_modules:
                category_key = reference.category_key.strip()
                if not category_key:
                    continue
                if category_key not in desired_keys:
                    desired_keys.append(category_key)
                track_weights[category_key] = max(track_weights.get(category_key, 0.0), weight)
                track_modules.setdefault(category_key, []).append((track, reference))
            if not track.recommended_modules:
                track_key = track.track_id.strip()
                if track_key and track_key not in desired_keys:
                    desired_keys.append(track_key)
                    track_weights.setdefault(track_key, weight)
        for outcome in goal_inference.target_outcomes:
            trimmed = outcome.strip()
            if trimmed and trimmed not in plan_copy.success_criteria:
                plan_copy.success_criteria.append(trimmed)

    average = _average_score(assessment_result)
    fallback_keys = _determine_foundation_keys(
        goal,
        average,
        existing_category_keys,
        len(plan_copy.modules),
    )
    for key in fallback_keys:
        if key not in desired_keys:
            desired_keys.append(key)

    tier_limit = _tier_limit(average)

    for key in desired_keys:
        template = _FOUNDATION_LIBRARY.get(key)
        if template is not None:
            if key not in existing_category_keys:
                focus_areas = list(template.focus_areas)
                for track, _ in track_modules.get(key, []):
                    for focus in track.focus_areas:
                        if focus not in focus_areas:
                            focus_areas.append(focus)
                weight = track_weights.get(key, template.weight)
                category_list.append(
                    EloCategoryDefinition(
                        key=template.key,
                        label=template.label,
                        description=template.description,
                        focus_areas=focus_areas,
                        weight=max(weight, 0.5),
                        rubric=[EloRubricBand(level=level, descriptor=descriptor) for level, descriptor in template.rubric],
                        starting_rating=1100,
                    )
                )
                existing_category_keys.add(key)
            else:
                if key in track_weights:
                    for category in category_list:
                        if category.key == key:
                            category.weight = max(category.weight, track_weights[key])
                            for track, _ in track_modules.get(key, []):
                                for focus in track.focus_areas:
                                    if focus not in category.focus_areas:
                                        category.focus_areas.append(focus)
                            break
            for track, reference in track_modules.get(key, []):
                module_id = reference.module_id.strip() or f"{track.track_id}-{len(existing_module_ids) + 1}"
                mapped = _MODULE_TEMPLATE_INDEX.get(module_id)
                if mapped and mapped[0] == key:
                    template_module = mapped[1]
                    _add_module_from_template(plan_copy, template_module, key, existing_module_ids)
                    continue
                if module_id in existing_module_ids:
                    continue
                focus_objectives = [f"Strengthen {area} proficiency." for area in track.focus_areas if area][:3]
                if not focus_objectives:
                    focus_objectives = [f"Deepen mastery of {track.label} essentials."]
                plan_copy.modules.append(
                    CurriculumModule(
                        module_id=module_id,
                        category_key=key,
                        title=f"{track.label}: {module_id.replace('-', ' ').title()}",
                        summary=reference.notes or track.notes or f"Applied practice sprint for {track.label}.",
                        objectives=focus_objectives,
                        activities=[],
                        deliverables=[f"Document learnings for {track.label} foundations."],
                        estimated_minutes=(reference.suggested_weeks or 1) * 180,
                    )
                )
                existing_module_ids.add(module_id)
            for module_template in template.modules:
                if module_template.tier > tier_limit:
                    continue
                _add_module_from_template(plan_copy, module_template, template.key, existing_module_ids)
            for criterion in template.success_criteria:
                if criterion not in plan_copy.success_criteria:
                    plan_copy.success_criteria.append(criterion)
            continue

        track = _find_track_for_category(goal_inference, key)
        if track is None:
            continue
        if key not in existing_category_keys:
            focus = [focus for focus in track.focus_areas if focus] or [track.label]
            rubric = _synthesise_rubric(track.label)
            category_list.append(
                EloCategoryDefinition(
                    key=key,
                    label=track.label,
                    description=track.notes or f"Establish durable foundations in {track.label}.",
                    focus_areas=focus,
                    weight=max(track_weights.get(key, track.weight or 1.0), 0.5),
                    rubric=rubric,
                    starting_rating=1100,
                )
            )
            existing_category_keys.add(key)
        for track_entry, reference in track_modules.get(key, []):
            module_id = reference.module_id.strip() or f"{track_entry.track_id}-{len(existing_module_ids) + 1}"
            if module_id in existing_module_ids:
                continue
            summary = reference.notes or track_entry.notes or f"Applied project work for {track_entry.label}."
            focus_objectives = [f"Practice {area} in real scenarios." for area in track_entry.focus_areas if area][:3]
            if not focus_objectives:
                focus_objectives = [f"Develop confidence executing {track_entry.label} workflows."]
            plan_copy.modules.append(
                CurriculumModule(
                    module_id=module_id,
                    category_key=key,
                    title=f"{track_entry.label} Foundations",
                    summary=summary,
                    objectives=focus_objectives,
                    activities=[],
                    deliverables=[f"Share reflection on {track_entry.label} practice."],
                    estimated_minutes=(reference.suggested_weeks or 1) * 180,
                )
            )
            existing_module_ids.add(module_id)

    for note in track_notes:
        if note not in plan_copy.success_criteria:
            plan_copy.success_criteria.append(note)

    return category_list, plan_copy


__all__ = ["ensure_foundational_curriculum"]
