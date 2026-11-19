import logging

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .ai_service import WebsiteFetchError, analyze_brand_from_url, generate_content_strategy, normalize_industry_label, normalize_target_audience, repair_strategy_sections
from .audience_service import format_audience_suggestion, suggest_audience
from .content_gap_service import research_content_gaps
from .competitor_discovery_service import discover_active_competitors
from .caption_analyzer_service import analyze_caption
from .profile_optimizer_service import optimize_profile, suggest_profile_cta
from .forms import AccountSettingsForm, BrandForm, BrandMemoryForm, BrandProfileForm, BrandDetailsForm, CaptionAnalyzerForm, ProfileOptimizerForm, EmailAuthenticationForm, PostResultForm, RepurposeForm, SignUpForm, StrategyBriefForm, StrategyOptionsForm, ReportInputForm, ReportReviewForm, REPORT_METRICS
from .models import BrandMemory, BrandProfile, ContentStrategy, MonthlyReport, PostResult, RepurposeProject
from .brand_memory import approved_brand_memory
from .reporting_service import build_report_pdf
from .report_workflow import prepare_report, build_guided_pdf
from .repurpose_service import generate_repurpose_package
from .strategy_service import generate_starter_strategy
from .strategy_quality import build_first_week_plan, validate_strategy
from .two_week_strategy import build_two_week_plan

logger = logging.getLogger(__name__)


def owned_brands(user):
    return BrandProfile.objects.filter(user=user).order_by("name")


def notify_ai_fallback(request, payload):
    if isinstance(payload, dict) and payload.get("_ai_provider") == "groq":
        messages.info(
            request,
            "Gemini was unavailable, so Sovaro completed this with its backup AI. Review the result as usual.",
        )


def normalize_website_url(value):
    url = (value or "").strip()
    if url.startswith("//"):
        url = f"https:{url}"
    elif not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    URLValidator(schemes=("http", "https"))(url)
    return url


def home(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    return render(request, "core/landing.html")


class SovaroLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


def signup(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("web:brand_create")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    brands = owned_brands(request.user)
    brand = brands.filter(id=request.GET.get("brand")).first() if request.GET.get("brand") else brands.first()
    strategy = brand.strategies.first() if brand else None
    reports = brand.reports.all()[:3] if brand else []
    return render(request, "core/dashboard.html", {
        "brands": brands, "brand": brand, "strategy": strategy, "reports": reports,
        "ideas": (strategy.content_ideas[:6] if strategy else []),
        "brand_count": brands.count(),
        "strategy_count": ContentStrategy.objects.filter(brand__user=request.user).count(),
        "report_count": MonthlyReport.objects.filter(brand__user=request.user).count(),
    })


@login_required
def account_settings(request):
    account_form = AccountSettingsForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST":
        if request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated securely.")
                return redirect("web:account_settings")
        else:
            account_form = AccountSettingsForm(request.POST, instance=request.user)
            if account_form.is_valid():
                account_form.save()
                messages.success(request, "Account settings updated.")
                return redirect("web:account_settings")
    return render(request, "core/account_settings.html", {
        "account_form": account_form,
        "password_form": password_form,
        "brand_count": owned_brands(request.user).count(),
    })


@login_required
def brand_create(request):
    form = BrandForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        brand = form.save(commit=False)
        brand.user = request.user
        brand.strategy_inputs = {
            "onboarding_status": "pending",
            "competitor_notes": form.cleaned_data.get("competitor_notes", "").strip(),
        }
        brand.save()
        messages.success(request, f"Review what Sovaro understands about {brand.name} before creating a strategy.")
        return redirect("web:brand_confirm", pk=brand.pk)
    return render(request, "core/brand_form.html", {"form": form, "page_title": "Create your brand workspace"})


@login_required
@require_http_methods(["GET", "POST"])
def brand_confirm(request, pk):
    brand = get_object_or_404(owned_brands(request.user), pk=pk)
    website_scan = bool((brand.strategy_inputs or {}).get("website_source"))
    short_industry = normalize_industry_label(
        brand.niche,
        (brand.strategy_inputs or {}).get("business_description", ""),
    )
    if short_industry != brand.niche:
        brand.niche = short_industry
        brand.save(update_fields=["niche", "updated_at"])
    short_audience = normalize_target_audience(brand.target_audience)
    if short_audience != brand.target_audience:
        inputs = dict(brand.strategy_inputs or {})
        inputs.setdefault("audience_detail", brand.target_audience)
        brand.target_audience = short_audience
        brand.strategy_inputs = inputs
        brand.save(update_fields=["target_audience", "strategy_inputs", "updated_at"])
    if request.method == "POST":
        if website_scan:
            owner_goal = request.POST.get("primary_goal", "").strip()
            owner_industry = request.POST.get("industry", "").strip()
            if not owner_goal:
                messages.error(request, "Add your business goal before confirming the website scan.")
                return redirect("web:brand_confirm", pk=brand.pk)
            if not owner_industry:
                messages.error(request, "Choose the correct industry before confirming the website scan.")
                return redirect("web:brand_confirm", pk=brand.pk)
            brand.primary_goal = owner_goal[:255]
            brand.niche = normalize_industry_label(owner_industry)
        inputs = dict(brand.strategy_inputs or {})
        inputs["onboarding_status"] = "confirmed"
        inputs["confirmed_at"] = timezone.now().isoformat()
        brand.strategy_inputs = inputs
        brand.save(update_fields=["strategy_inputs", "primary_goal", "niche", "updated_at"])
        messages.success(request, "Brand profile saved. Sovaro will use these owner-approved details in future plans.")
        return redirect("web:brand_detail", pk=brand.pk)
    return render(request, "core/brand_confirm.html", {
        "brand": brand,
        "website_scan": website_scan,
        "is_confirmed": (brand.strategy_inputs or {}).get("onboarding_status") == "confirmed",
    })


@login_required
@require_http_methods(["POST"])
def audience_suggestion(request):
    try:
        import json
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return JsonResponse({"error": "We could not read those brand details."}, status=400)

    values = {
        "brand_name": str(payload.get("brand_name", "")).strip()[:255],
        "niche": str(payload.get("niche", "")).strip()[:255],
        "business_model": str(payload.get("business_model", "")).strip()[:100],
        "primary_goal": str(payload.get("primary_goal", "")).strip()[:255],
    }
    if not values["niche"] or not values["business_model"]:
        return JsonResponse({"error": "Add the industry and business model first."}, status=400)

    suggestion = suggest_audience(**values)
    return JsonResponse({
        "suggestion": format_audience_suggestion(suggestion),
        "source": suggestion["source"],
    })


@login_required
@require_http_methods(["POST"])
def competitor_suggestion(request):
    try:
        import json
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return JsonResponse({"error": "We could not read those brand details."}, status=400)
    brand_name = str(payload.get("brand_name", "")).strip()[:255]
    industry = str(payload.get("industry", "")).strip()[:120]
    audience = str(payload.get("audience", "")).strip()[:500]
    location = str(payload.get("location", "")).strip()[:120]
    if not industry:
        return JsonResponse({"error": "Add the industry before searching for competitors."}, status=400)
    try:
        result = discover_active_competitors(brand_name, industry, audience, location)
    except Exception:
        return JsonResponse({
            "error": "Live competitor search is unavailable right now. No competitors were invented; you can add known brands manually."
        }, status=503)
    return JsonResponse(result)


@login_required
def brand_scan(request):
    if request.method == "POST":
        url = request.POST.get("url", "").strip()
        if not url:
            messages.error(request, "Enter a website URL to scan.")
        else:
            try:
                url = normalize_website_url(url)
                data = analyze_brand_from_url(url)
                brand = BrandProfile.objects.create(
                    user=request.user,
                    name=data.get("brand_name") or "Unnamed brand",
                    niche=data.get("niche") or "General",
                    business_model=data.get("business_model") or "b2b_saas",
                    target_audience=data.get("target_audience") or "To be refined",
                    primary_goal="",
                    tone_of_voice=data.get("tone_of_voice") or "Clear and approachable",
                    brand_values=data.get("brand_values", []),
                    content_themes=data.get("content_themes", []),
                    social_profiles=data.get("social_profiles", {}),
                    social_assessment=data.get("social_assessment", {}),
                    conversion_url=url,
                    strategy_inputs={
                        "onboarding_status": "pending",
                        "website_source": url,
                        "business_description": data.get("business_description", ""),
                        "audience_detail": data.get("audience_detail", ""),
                        "audience_needs": data.get("audience_needs", ""),
                        "audience_barriers": data.get("audience_barriers", ""),
                    },
                )
                messages.success(request, "Website analysed. Confirm the drafted details before Sovaro uses them as facts.")
                return redirect("web:brand_confirm", pk=brand.pk)
            except ValidationError:
                messages.error(request, "Enter a valid website such as yourbrand.com or www.yourbrand.com.")
            except WebsiteFetchError as exc:
                if exc.status_code == 403:
                    messages.error(request, "This website blocked the automatic scan (403). No AI model ran. You can add the brand details manually instead.")
                else:
                    messages.error(request, f"The website scan stopped before AI analysis: {exc} You can add the brand details manually.")
            except Exception as exc:
                messages.error(request, f"We could not analyse that site: {exc}")
    return render(request, "core/brand_scan.html")


@login_required
def brand_detail(request, pk):
    brand = get_object_or_404(owned_brands(request.user), pk=pk)
    return render(request, "core/brand_detail.html", {
        "brand": brand, "strategy": brand.strategies.first(), "form": StrategyOptionsForm(),
        "brief_form": StrategyBriefForm(initial={"competitor_notes": (brand.strategy_inputs or {}).get("competitor_notes", ""), **brand.strategy_inputs}),
    })


@login_required
@require_http_methods(["POST"])
def brand_delete(request, pk):
    brand = get_object_or_404(owned_brands(request.user), pk=pk)
    brand_name = brand.name
    brand.delete()
    messages.success(request, f"{brand_name} was removed from your workspace.")
    return redirect("web:dashboard")


@login_required
def brand_profile(request, pk):
    brand = get_object_or_404(owned_brands(request.user), pk=pk)
    image_post = request.method == "POST" and (request.POST.get("form_type") == "image" or "brand_image" in request.FILES)
    details_post = request.method == "POST" and request.POST.get("form_type") == "details"
    form = BrandProfileForm(request.POST if image_post else None, request.FILES if image_post else None, instance=brand)
    details_form = BrandDetailsForm(request.POST if details_post else None, instance=brand)
    if image_post and form.is_valid():
        form.save()
        messages.success(request, "Brand image updated.")
        return redirect("web:brand_profile", pk=brand.pk)
    if details_post and details_form.is_valid():
        details_form.save()
        messages.success(request, "Brand details updated.")
        return redirect("web:brand_confirm" if (brand.strategy_inputs or {}).get("onboarding_status") == "pending" else "web:brand_profile", pk=brand.pk)
    return render(request, "core/brand_profile.html", {"brand": brand, "form": form, "details_form": details_form})


@login_required
def brand_memory(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    memory = None
    memory_id = request.POST.get("memory_id") if request.method == "POST" else request.GET.get("edit")
    if memory_id:
        memory = get_object_or_404(BrandMemory, pk=memory_id, brand=brand)
    form = BrandMemoryForm(request.POST or None, instance=memory)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.brand = brand
        saved.source = "user"
        saved.is_active = True
        saved.save()
        messages.success(request, "Brand memory updated." if memory else "Brand memory saved.")
        return redirect("web:brand_memory", brand_pk=brand.pk)
    return render(request, "core/brand_memory.html", {
        "brand": brand,
        "form": form,
        "editing_memory": memory,
        "memories": brand.memories.filter(is_active=True).exclude(source="onboarding"),
        "confirmed_count": brand.memories.filter(is_active=True, status="confirmed").exclude(source="onboarding").count(),
    })


@login_required
@require_http_methods(["POST"])
def brand_memory_status(request, brand_pk, memory_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    memory = get_object_or_404(BrandMemory, pk=memory_pk, brand=brand)
    status = request.POST.get("status")
    allowed = {value for value, _ in BrandMemory.STATUS_CHOICES}
    if status in allowed:
        memory.status = status
        memory.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Memory marked as {memory.get_status_display().lower()}.")
    return redirect("web:brand_memory", brand_pk=brand.pk)


@login_required
@require_http_methods(["POST"])
def brand_memory_delete(request, brand_pk, memory_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    memory = get_object_or_404(BrandMemory, pk=memory_pk, brand=brand)
    memory.delete()
    messages.success(request, "Brand memory removed.")
    return redirect("web:brand_memory", brand_pk=brand.pk)


@login_required
@require_http_methods(["POST"])
def strategy_brief_save(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    brief_form = StrategyBriefForm(request.POST)
    if brief_form.is_valid():
        brand.strategy_inputs = {**(brand.strategy_inputs or {}), **{
            key: str(value) if value is not None else ""
            for key, value in brief_form.cleaned_data.items()
        }}
        brand.save(update_fields=["strategy_inputs", "updated_at"])
        messages.success(request, "Strategy brief saved. You can now generate a plan.")
        return redirect("web:brand_detail", pk=brand.pk)
    return render(request, "core/brand_detail.html", {
        "brand": brand, "strategy": brand.strategies.first(),
        "form": StrategyOptionsForm(), "brief_form": brief_form,
    })


@login_required
@require_http_methods(["POST"])
def strategy_generate(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    two_week_trial = request.POST.get("plan_horizon") == "14"
    if (brand.strategy_inputs or {}).get("onboarding_status") == "pending":
        messages.warning(request, "Confirm the brand foundation before generating a strategy.")
        return redirect("web:brand_confirm", pk=brand.pk)
    form = StrategyOptionsForm(request.POST)
    brief_form = StrategyBriefForm(request.POST)
    options_valid = form.is_valid()
    brief_valid = brief_form.is_valid()
    if not options_valid or not brief_valid:
        messages.error(request, "Please correct the highlighted details below.")
        return render(request, "core/brand_detail.html", {
            "brand": brand, "strategy": brand.strategies.first(),
            "form": form, "brief_form": brief_form,
        })
    brand.strategy_inputs = {**(brand.strategy_inputs or {}), **{
        key: str(value) if value is not None else ""
        for key, value in brief_form.cleaned_data.items()
    }}
    brand.save(update_fields=["strategy_inputs", "updated_at"])
    try:
        starter = generate_starter_strategy(
            brand, form.cleaned_data["platforms"], form.cleaned_data["posts_per_week"]
        )
        if form.cleaned_data["mode"] == "ai":
            try:
                data = generate_content_strategy(
                    brand_name=brand.name, brand_niche=brand.niche,
                    target_audience=brand.target_audience, tone_of_voice=brand.tone_of_voice,
                    business_model=brand.business_model, primary_goal=brand.primary_goal,
                    weekly_posts_capacity=brand.weekly_posts_capacity,
                    conversion_url=brand.conversion_url or "",
                    negative_guardrails=brand.negative_guardrails,
                    brand_values=brand.brand_values, content_themes=brand.content_themes,
                    target_platforms=form.cleaned_data["platforms"],
                    posts_per_week=form.cleaned_data["posts_per_week"],
                    content_formats=brand.content_formats,
                    strategy_inputs=brand.strategy_inputs,
                    brand_memory=approved_brand_memory(brand),
                )
                data["strategy_foundation"] = starter["strategy_foundation"]
            except Exception as exc:
                logger.exception("Strategy AI failed after provider fallback: brand_id=%s error_type=%s", brand.pk, type(exc).__name__)
                data = starter
                messages.warning(request, "AI assistance is temporarily unavailable. We created a basic draft so your work is not lost; retry later for the fully tailored strategy.")
        else:
            data = starter
        if data is starter:
            data["_generation_mode"] = "starter"
        data["weekly_plan"] = build_first_week_plan(brand, data)
        research = {}
        if two_week_trial:
            previous = brand.strategies.first()
            if previous and (previous.content_gap_research or {}).get("source_status") == "grounded":
                research = previous.content_gap_research
            else:
                research = research_content_gaps(brand)
            data["strategy_foundation"]["plan_horizon_days"] = 14
            data["strategy_foundation"]["two_week_plan"] = build_two_week_plan(brand, data, research)
        validation_report = validate_strategy(brand, data)
        if validation_report["errors"] and data.get("_ai_provider") and data.get("_generation_mode") != "starter":
            try:
                data = repair_strategy_sections(brand, data, validation_report["errors"])
                data["strategy_foundation"] = starter["strategy_foundation"] | {
                    key: value for key, value in (data.get("strategy_foundation") or {}).items()
                    if key in ("plan_horizon_days", "two_week_plan")
                }
                data["weekly_plan"] = build_first_week_plan(brand, data)
                if two_week_trial:
                    data["strategy_foundation"]["plan_horizon_days"] = 14
                    data["strategy_foundation"]["two_week_plan"] = build_two_week_plan(brand, data, research)
                validation_report = validate_strategy(brand, data)
                validation_report["repair_attempted"] = True
            except Exception as exc:
                logger.warning("Strategy repair failed: brand_id=%s error_type=%s", brand.pk, type(exc).__name__)
                validation_report["repair_attempted"] = True
                validation_report["warnings"].append("Automatic revision was unavailable. Review the listed issues before sharing.")
        notify_ai_fallback(request, data)
        if validation_report["errors"]:
            messages.error(request, "The strategy did not pass its quality checks. Review the validation report before using it.")
        strategy = ContentStrategy.objects.create(
            brand=brand, strategy_foundation=data.get("strategy_foundation", {}),
            executive_summary=data.get("executive_summary", ""),
            audience_icp_dossier=data.get("audience_icp_dossier", {}), content_pillars=data.get("content_pillars", []),
            platform_playbook=data.get("platform_playbook", []), content_mix=data.get("content_mix", {}),
            posting_schedule=data.get("posting_schedule", []), content_ideas=data.get("content_ideas", []),
            kpis=data.get("kpis", []), cta_strategy=data.get("cta_strategy", []),
            weekly_plan=data.get("weekly_plan", []), validation_report=validation_report,
            content_gap_research=research,
        )
        if validation_report["status"] == "passed":
            messages.success(request, "Strategy draft created. Review the details before sharing.")
        elif not validation_report["errors"]:
            messages.warning(request, "Strategy draft created, but its review notes need attention before sharing.")
        return redirect("web:strategy_detail", pk=strategy.pk)
    except Exception as exc:
        messages.error(request, f"Strategy generation failed: {exc}")
        return redirect("web:brand_detail", pk=brand.pk)


@login_required
def strategy_detail(request, pk):
    strategy = get_object_or_404(ContentStrategy, pk=pk, brand__user=request.user)
    executive_summary = strategy.executive_summary
    if executive_summary.startswith("Draft direction:"):
        executive_summary = executive_summary.replace("Draft direction:", "The recommended direction is to", 1)
        executive_summary = executive_summary.replace(
            "Confirm the open assumptions before sharing this plan with a client.",
            "Results should be reviewed after 30 days and used to refine the next phase.",
        )
    template = "core/two_week_strategy.html" if strategy.strategy_foundation.get("plan_horizon_days") == 14 else "core/strategy_detail.html"
    return render(request, template, {
        "strategy": strategy,
        "brand": strategy.brand,
        "client_executive_summary": executive_summary,
        "can_share": (strategy.validation_report or {}).get("status") in ("passed", "review"),
        "recorded_plan_keys": set(strategy.post_results.values_list("plan_key", flat=True)),
    })


@login_required
@require_http_methods(["GET", "POST"])
def strategy_results(request, pk):
    strategy = get_object_or_404(ContentStrategy, pk=pk, brand__user=request.user)
    initial = {}
    plan_key = request.GET.get("plan") or request.POST.get("plan_key") or ""
    if plan_key:
        slot = next((item for item in strategy.weekly_plan if item.get("key") == plan_key), None)
        if slot:
            initial = {"plan_key": plan_key, "title": slot.get("hook", ""), "platform": slot.get("platform", "")}
    form = PostResultForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        result = form.save(commit=False)
        result.brand = strategy.brand
        result.strategy = strategy
        result.save()
        if result.lesson.strip():
            BrandMemory.objects.create(
                brand=strategy.brand,
                category="performance_lesson",
                statement=result.lesson.strip(),
                evidence=(
                    f"Post: {result.title}. Platform: {result.platform or 'Not specified'}. "
                    f"Reach {result.reach}; views {result.views}; saves {result.saves}; shares {result.shares}; "
                    f"comments {result.comments}; clicks {result.link_clicks}; enquiries {result.enquiries}; sales {result.sales}."
                ),
                status="confirmed",
                source="post_result",
            )
        messages.success(request, "Result saved. The confirmed lesson is now available to future strategy work.")
        return redirect("web:strategy_results", pk=strategy.pk)
    return render(request, "core/strategy_results.html", {
        "brand": strategy.brand,
        "strategy": strategy,
        "form": form,
        "results": strategy.post_results.all(),
    })


@login_required
def ideas(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    strategy = brand.strategies.first()
    return render(request, "core/ideas.html", {
        "brand": brand,
        "strategy": strategy,
        "ideas": strategy.content_ideas if strategy else [],
        "research": strategy.content_gap_research if strategy else {},
    })


@login_required
@require_http_methods(["POST"])
def research_content_gaps_view(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    strategy = brand.strategies.first()
    if not strategy:
        messages.error(request, "Create a strategy before researching content gaps.")
        return redirect("web:brand_detail", pk=brand.pk)
    try:
        previous_research_status = (strategy.content_gap_research or {}).get("source_status")
        research = research_content_gaps(brand)
        ideas = research.get("ideas") or []
        strategy.content_gap_research = research
        strategy.content_gap_researched_at = timezone.now()
        update_fields = ["content_gap_research", "content_gap_researched_at", "updated_at"]
        if ideas:
            strategy.content_ideas = ideas
            update_fields.append("content_ideas")
        elif research.get("source_status") == "research_unavailable" and previous_research_status == "starter_fallback":
            # Remove ideas created by the retired generic fallback, while
            # preserving genuine strategy or grounded-research ideas.
            strategy.content_ideas = []
            update_fields.append("content_ideas")
        strategy.save(update_fields=update_fields)
        if research.get("source_status") == "research_unavailable":
            messages.warning(request, "Live research was unavailable. Sovaro did not invent gaps or replace your existing ideas. Add real competitor or customer evidence and try again.")
        else:
            messages.success(request, f"Found {len(research.get('content_gaps') or [])} content gaps and built {len(ideas)} evidence-led ideas.")
    except Exception as exc:
        messages.error(request, f"We could not complete grounded research: {exc}")
    return redirect("web:ideas", brand_pk=brand.pk)


@login_required
def repurpose_studio(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    form = RepurposeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            package = generate_repurpose_package(brand, form.cleaned_data)
            notify_ai_fallback(request, package)
            project = RepurposeProject.objects.create(
                brand=brand,
                mode=form.cleaned_data["mode"],
                source_title=form.cleaned_data["source_title"],
                source_content=form.cleaned_data["source_content"],
                platforms=form.cleaned_data["platforms"],
                objective=form.cleaned_data["objective"],
                desired_action=form.cleaned_data["desired_action"],
                source_analysis=package.get("source_analysis", {}),
                hook_options=package.get("hook_options", []),
                outputs=package.get("outputs", []),
                quality_report=package.get("quality_report", {}),
            )
            messages.success(request, f"Created {len(project.outputs)} platform-native drafts.")
            return redirect("web:repurpose_detail", pk=project.pk)
        except Exception as exc:
            messages.error(request, f"Repurposing failed: {exc}")
    return render(request, "core/repurpose_studio.html", {
        "brand": brand,
        "form": form,
        "projects": brand.repurpose_projects.all()[:6],
    })


@login_required
def repurpose_detail(request, pk):
    project = get_object_or_404(RepurposeProject, pk=pk, brand__user=request.user)
    return render(request, "core/repurpose_detail.html", {"project": project, "brand": project.brand})


@login_required
def caption_analyzer(request):
    return render(request, "core/caption_coming_soon.html")


@login_required
def profile_optimizer(request):
    brands = list(owned_brands(request.user))
    brand_presets = {}
    for brand in brands:
        inputs = brand.strategy_inputs or {}
        profiles = brand.social_profiles or {}
        selected_platform = next((key for key in ("instagram", "tiktok", "linkedin", "x", "youtube") if profiles.get(key)), "")
        if not selected_platform and profiles.get("twitter"):
            selected_platform = "x"
        if not selected_platform:
            suggested = (brand.social_assessment or {}).get("primary_channels") or []
            selected_platform = str(suggested[0]).lower() if suggested and str(suggested[0]).lower() in ("instagram", "tiktok", "linkedin", "x", "youtube") else ""
        goal = (brand.primary_goal or "").lower()
        profile_goal = "sales" if any(word in goal for word in ("sale", "sell", "purchase", "order")) else "leads" if any(word in goal for word in ("lead", "enquir", "book", "client")) else "community" if "communit" in goal else "authority" if any(word in goal for word in ("author", "trust")) else "discovery"
        brand_presets[str(brand.pk)] = {
            "saved_brand": str(brand.pk),
            "platform": selected_platform,
            "profile_goal": profile_goal,
            "profile_reference": profiles.get(selected_platform) or (profiles.get("twitter") if selected_platform == "x" else "") or "",
            "business_name": brand.name,
            "industry": brand.niche[:180],
            "audience": brand.target_audience[:300],
            "offer": (inputs.get("offer_details") or inputs.get("business_description") or "")[:300],
            "differentiator": (inputs.get("differentiators") or "")[:300],
            "service_area": (inputs.get("service_area") or "")[:180],
            "proof_points": (inputs.get("proof_available") or "")[:400],
            "brand_voice": brand.tone_of_voice or "",
            "claims_to_avoid": brand.negative_guardrails or "",
            "destination": brand.conversion_url or "",
            "desired_cta": inputs.get("desired_cta") or suggest_profile_cta(profile_goal, brand.primary_goal, brand.conversion_url or ""),
            "cta_is_suggested": not bool(inputs.get("desired_cta")),
        }
    selected_preset = brand_presets.get(request.GET.get("brand", "")) if request.method == "GET" else None
    form = ProfileOptimizerForm(request.POST or None, brands=brands, initial=selected_preset or {})
    result = None
    if request.method == "POST" and form.is_valid():
        result = optimize_profile(form.cleaned_data)
        if result.get("analysis_mode") == "rule_based":
            messages.warning(request, "The AI auditor was unavailable, so Sovaro provided a basic structural audit and optimized draft.")
        else:
            notify_ai_fallback(request, result)
    return render(request, "core/profile_optimizer.html", {
        "form": form, "result": result, "brand_presets": brand_presets,
        "has_saved_brands": bool(brands),
    })


@login_required
def reports(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    return render(request, "core/reports.html", {"brand": brand, "reports": brand.reports.all()})


@login_required
def report_create(request, brand_pk):
    brand = get_object_or_404(owned_brands(request.user), pk=brand_pk)
    form = ReportInputForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            data = prepare_report(form.cleaned_data)
        except ValueError as exc:
            form.add_error("csv_file", str(exc))
        else:
            report = MonthlyReport.objects.create(brand=brand, **data)
            messages.success(request, "Report draft created. Review the story before sharing it.")
            return redirect("web:report_detail", pk=report.pk)
    metric_pairs = [(form[f"current_{key}"], form[f"previous_{key}"]) for key, _ in REPORT_METRICS]
    return render(request, "core/report_create.html", {"brand": brand, "form": form, "metric_pairs": metric_pairs})


@login_required
def report_edit_data(request, pk):
    report = get_object_or_404(MonthlyReport, pk=pk, brand__user=request.user, data_provenance__in=("guided_entry", "guided_csv"))
    initial = {"month": report.start_date, "platform": ", ".join(report.platforms_covered), "competitor_snapshot": report.competitor_snapshot}
    for key, _ in REPORT_METRICS:
        initial[f"current_{key}"] = report.raw_metrics.get(key)
        initial[f"previous_{key}"] = report.previous_period_metrics.get(key)
    initial["top_posts"] = "\n".join(" | ".join((str(p.get("title", "")), str(p.get("format", "")), str(p.get("impressions", "")), str(p.get("engagements", "")), str(p.get("url", "")))) for p in (report.content_performance or {}).get("top_posts", []))
    form = ReportInputForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            data = prepare_report(form.cleaned_data)
        except ValueError as exc:
            form.add_error("csv_file", str(exc))
        else:
            for field in ("month_year", "start_date", "end_date", "platforms_covered", "raw_metrics", "previous_period_metrics", "scorecard_data", "post_records", "content_performance", "data_provenance", "competitor_snapshot", "executive_summary", "what_worked", "next_month_plan"):
                setattr(report, field, data[field])
            report.status = "draft"
            report.save()
            messages.success(request, "Results updated. Review the report story again before sharing.")
            return redirect("web:report_detail", pk=report.pk)
    metric_pairs = [(form[f"current_{key}"], form[f"previous_{key}"]) for key, _ in REPORT_METRICS]
    return render(request, "core/report_create.html", {"brand": report.brand, "form": form, "metric_pairs": metric_pairs, "report": report})


@login_required
def report_detail(request, pk):
    report = get_object_or_404(MonthlyReport, pk=pk, brand__user=request.user)
    form = ReportReviewForm(request.POST or None, instance=report)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Report saved.")
        return redirect("web:report_detail", pk=report.pk)
    return render(request, "core/report_detail.html", {"report": report, "brand": report.brand, "form": form, "scorecard": (report.scorecard_data or {}).values(), "top_posts": (report.content_performance or {}).get("top_posts", [])})


@login_required
def report_pdf(request, pk):
    report = get_object_or_404(MonthlyReport, pk=pk, brand__user=request.user)
    pdf = build_guided_pdf(report) if report.data_provenance in ("guided_entry", "guided_csv") else build_report_pdf(report)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Sovaro-Report-{report.id}.pdf"'
    return response
