import json
import os
import tempfile
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import Mock, patch

from .models import BrandMemory, BrandProfile, ContentStrategy, MonthlyReport, PostResult, RepurposeProject
from .brand_memory import approved_brand_memory
from .content_gap_service import research_content_gaps
from .ai_service import clean_and_normalize_strategy, generate_content_strategy, generate_with_fallback, normalize_industry_label, normalize_target_audience, repair_strategy_sections
from .ai_service import WebsiteFetchError
from .strategy_service import generate_starter_strategy
from .profile_optimizer_service import suggest_profile_cta
from .strategy_quality import build_first_week_plan, validate_strategy
from .two_week_strategy import build_two_week_plan


class StrategyQualityGateTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="quality@example.com", password="test-password")
        self.brand = BrandProfile.objects.create(
            user=user, name="Face Facts", niche="Skincare", target_audience="Adults with oily skin",
            primary_goal="Generate 30 qualified enquiries in 90 days", weekly_posts_capacity=3,
        )

    def test_week_one_respects_platform_allocation(self):
        data = generate_starter_strategy(self.brand, "Instagram,TikTok", 3)
        data["posting_schedule"] = [
            {"platform": "Instagram", "frequency": "2 posts per week"},
            {"platform": "TikTok", "frequency": "1 post per week"},
        ]
        data["weekly_plan"] = build_first_week_plan(self.brand, data)
        self.assertEqual([post["platform"] for post in data["weekly_plan"]], ["Instagram", "Instagram", "TikTok"])
        self.assertNotIn("Week-one posts do not match", " ".join(validate_strategy(self.brand, data)["errors"]))

    def test_empty_kpis_and_unconfirmed_price_block_sharing(self):
        data = generate_starter_strategy(self.brand, "Instagram", 3)
        data["weekly_plan"] = build_first_week_plan(self.brand, data)
        data["kpis"] = []
        data["content_ideas"][0]["concept"] = "Buy our £15 treatment today."
        report = validate_strategy(self.brand, data)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("primary measure" in error for error in report["errors"]))
        self.assertTrue(any("price" in error for error in report["errors"]))

    def test_two_week_plan_keeps_capacity_and_labels_public_evidence(self):
        data = generate_starter_strategy(self.brand, "Instagram,TikTok", 3)
        data["posting_schedule"] = [
            {"platform": "Instagram", "frequency": "2 posts per week"},
            {"platform": "TikTok", "frequency": "1 post per week"},
        ]
        research = {"source_status": "grounded", "ideas": [{
            "platform": "Instagram", "hook": "A sourced customer question", "concept": "Answer the question",
            "source_url": "https://www.instagram.com/p/example/", "format": "Carousel",
        }]}
        plan = build_two_week_plan(self.brand, data, research)
        self.assertEqual(len(plan), 6)
        self.assertEqual([post["platform"] for post in plan[:3]], ["Instagram", "Instagram", "TikTok"])
        self.assertEqual(plan[0]["source_url"], "https://www.instagram.com/p/example/")
        self.assertEqual(plan[0]["evidence_status"], "Public source linked; performance unverified")

    def test_four_brand_types_keep_their_goal_and_platforms(self):
        cases = [
            ("Luma Skin", "Skincare", "Generate 30 enquiries", "enquiries", "Instagram,TikTok"),
            ("Joshua Motors", "Car dealership", "Sell 20 cars", "sales", "Instagram,Facebook"),
            ("Joy Cakes", "Bakery", "Get 12 cake bookings", "bookings", "Instagram"),
            ("Automaark", "Business software", "Generate 10 qualified leads", "leads", "LinkedIn"),
        ]
        for name, niche, goal, metric, platforms in cases:
            with self.subTest(name=name):
                self.brand.name, self.brand.niche, self.brand.primary_goal = name, niche, goal
                self.brand.strategy_inputs = {"goal_metric": metric, "brand_stage": "new"}
                data = generate_starter_strategy(self.brand, platforms, 3)
                data["executive_summary"] = f"{name} will test a practical publishing plan to support {goal.lower()} through customer questions and clear next steps."
                data["weekly_plan"] = build_first_week_plan(self.brand, data)
                report = validate_strategy(self.brand, data)
                self.assertEqual(data["strategy_foundation"]["owner_stated_goal"], goal)
                self.assertFalse(any("unselected platform" in error or "primary KPI" in error for error in report["errors"]))

    def test_unselected_platform_and_unproved_result_are_blocked(self):
        self.brand.strategy_inputs = {"goal_metric": "enquiries"}
        data = generate_starter_strategy(self.brand, "Instagram", 3)
        data["executive_summary"] = "Face Facts will answer customer questions to support the owner's enquiry goal while testing its first month."
        data["platform_playbook"].append({"platform": "LinkedIn"})
        data["content_ideas"][0]["claim_classification"] = "evidence_backed"
        data["weekly_plan"] = build_first_week_plan(self.brand, data)
        report = validate_strategy(self.brand, data)
        self.assertTrue(any("unselected platform" in error for error in report["errors"]))
        self.assertTrue(any("no brand proof" in error for error in report["errors"]))

    def test_changed_owner_target_is_blocked(self):
        self.brand.primary_goal = "Generate 30 qualified enquiries in 90 days"
        data = generate_starter_strategy(self.brand, "Instagram", 3)
        data["strategy_foundation"]["goal"] = "Generate 20 qualified enquiries in 90 days"
        data["executive_summary"] = "Face Facts will answer customer questions to support qualified enquiries while testing its first month."
        data["weekly_plan"] = build_first_week_plan(self.brand, data)
        report = validate_strategy(self.brand, data)
        self.assertTrue(any("numerical target" in error for error in report["errors"]))

    def test_owner_supplied_target_survives_normalization_without_baseline(self):
        raw = {"kpis": [{"primary_kpi": "Qualified enquiries", "monthly_targets": "30 qualified enquiries in 90 days"}]}
        result = clean_and_normalize_strategy(raw, strategy_inputs={"owner_goal": "Generate 30 qualified enquiries in 90 days"})
        self.assertEqual(result["kpis"][0]["monthly_targets"], "30 qualified enquiries in 90 days")

    @patch("core.ai_service.generate_with_fallback")
    def test_prompt_has_one_idea_count_and_no_brand_specific_template(self, generator):
        generator.return_value = SimpleNamespace(text='{"content_ideas": []}', provider="gemini", model="test")
        generate_content_strategy("Joy Cakes", "Bakery", "Lagos families", "Warm", primary_goal="Get cake bookings")
        prompt = generator.call_args.args[0]
        self.assertIn("exactly 12 high-quality content ideas", prompt)
        self.assertNotIn("30 ideas", prompt)
        self.assertNotIn("Paystack", prompt)
        self.assertIn("EVIDENCE RULE OVERRIDES", prompt)

    @patch("core.ai_service.generate_with_fallback")
    def test_repair_requests_only_failing_sections(self, generator):
        generator.return_value = SimpleNamespace(text='{"kpis": [{"primary_kpi": "Qualified enquiries", "monthly_targets": "30 in 90 days"}]}', provider="gemini", model="test")
        self.brand.strategy_inputs = {"goal_metric": "enquiries"}
        data = generate_starter_strategy(self.brand, "Instagram", 3)
        data["kpis"] = []
        repaired = repair_strategy_sections(self.brand, data, ["Add a primary measure and a target or baseline plan before sharing."])
        self.assertEqual(repaired["kpis"][0]["primary_kpi"], "Qualified enquiries")
        self.assertIn("exactly these keys: kpis", generator.call_args.args[0])


class AIProviderFallbackTests(TestCase):
    def test_long_positioning_is_reduced_to_short_industry_category(self):
        self.assertEqual(
            normalize_industry_label("AI-Powered Innovation and Intellectual Property Monetization Platform"),
            "Technology",
        )
        self.assertEqual(normalize_industry_label("Project Management Software"), "Project Management")
        self.assertEqual(
            normalize_target_audience(
                "Creators, innovators, investors, entrepreneurs, and forward-thinking organizations looking to conceptualize and monetize ideas"
            ),
            "Creators, innovators, investors, entrepreneurs, and forward-thinking organizations",
        )

    @patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-test", "GROQ_API_KEY": "groq-test"}, clear=False)
    @patch("core.ai_service.requests.post")
    @patch("core.ai_service.get_gemini_client", side_effect=RuntimeError("Gemini quota exhausted"))
    def test_groq_is_used_when_gemini_is_unavailable(self, _gemini, post):
        groq_response = Mock()
        groq_response.raise_for_status.return_value = None
        groq_response.json.return_value = {
            "choices": [{"message": {"content": '{"status":"ok"}'}}]
        }
        post.return_value = groq_response

        response = generate_with_fallback("Return JSON with a status field.")

        self.assertEqual(response.text, '{"status":"ok"}')
        self.assertEqual(response.provider, "groq")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "openai/gpt-oss-120b")

    @patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-test", "GROQ_API_KEY": "groq-test"}, clear=False)
    @patch("core.ai_service.requests.post")
    @patch("core.ai_service.get_gemini_client")
    def test_gemini_remains_the_primary_provider(self, get_client, post):
        generated = SimpleNamespace(text='{"provider":"gemini"}')
        client = Mock()
        client.models.generate_content.return_value = generated
        get_client.return_value = client

        response = generate_with_fallback("Return JSON.")

        self.assertEqual(response.text, generated.text)
        self.assertEqual(response.provider, "gemini")
        post.assert_not_called()


class BrowserWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.com", email="owner@example.com", password="safe-test-password"
        )
        self.brand = BrandProfile.objects.create(
            user=self.user,
            name="Example Co",
            niche="B2B SaaS",
            target_audience="Operations leaders",
        )

    def test_home_is_a_public_landing_page(self):
        response = self.client.get(reverse("web:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stop guessing what to post")
        self.assertContains(response, reverse("web:signup"))
        self.assertContains(response, "data-theme-toggle")
        self.assertContains(response, "core/theme.js")

    def test_authenticated_layout_has_mobile_logout_control(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:dashboard"))
        self.assertContains(response, 'class="mobile-logout-form"', html=False)
        self.assertContains(response, 'aria-label="Log out"', html=False)
        self.assertContains(response, reverse("web:logout"))

    def test_signed_in_home_redirects_to_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:home"))
        self.assertRedirects(response, reverse("web:dashboard"))

    def test_new_signup_goes_to_brand_setup(self):
        response = self.client.post(reverse("web:signup"), {
            "first_name": "New", "email": "new@example.com",
            "password1": "another-safe-test-password", "password2": "another-safe-test-password",
        })
        self.assertRedirects(response, reverse("web:brand_create"))

    def test_brand_pages_require_a_session(self):
        response = self.client.get(reverse("web:brand_detail", args=[self.brand.pk]))
        self.assertRedirects(response, f'{reverse("web:login")}?next={reverse("web:brand_detail", args=[self.brand.pk])}', fetch_redirect_response=False)

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(reverse("web:login"), {
            "username": "owner@example.com", "password": "safe-test-password",
        })
        self.assertRedirects(response, reverse("web:dashboard"))

    def test_account_settings_update_identity_and_keep_unique_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:account_settings"), {
            "action": "account",
            "first_name": "Ada",
            "email": "ada@example.com",
        })
        self.assertRedirects(response, reverse("web:account_settings"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ada")
        self.assertEqual(self.user.email, "ada@example.com")
        self.assertEqual(self.user.username, "ada@example.com")
        self.assertEqual(self.client.get(reverse("web:account_settings")).status_code, 200)

    def test_owner_can_view_brand_workspace(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:brand_detail", args=[self.brand.pk]))
        self.assertContains(response, "Example Co")

    def test_owner_can_upload_brand_profile_image(self):
        self.client.force_login(self.user)
        image = SimpleUploadedFile(
            "brand.gif",
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("web:brand_profile", args=[self.brand.pk]),
                {"brand_image": image},
            )
            self.assertRedirects(response, reverse("web:brand_profile", args=[self.brand.pk]))
            self.brand.refresh_from_db()
            self.assertTrue(self.brand.brand_image.name.endswith("brand.gif"))

    def test_add_brand_uses_guided_two_column_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:brand_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-brand-progress")
        self.assertContains(response, "data-brand-form")
        self.assertContains(response, "brand-setup-form")
        self.assertContains(response, "Suggest with AI")
        self.assertContains(response, "Warm &amp; approachable")
        self.assertContains(response, "Other / create a custom tone")
        self.assertContains(response, "Find active competitors")
        self.assertContains(response, "data-competitor-suggest")

    def test_custom_brand_tone_is_saved(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:brand_create"), {
            "name": "Founder Lab",
            "niche": "Startup education",
            "business_model": "professional_services",
            "primary_goal": "Generate qualified enquiries",
            "weekly_posts_capacity": 4,
            "conversion_url": "",
            "target_audience": "Early-stage founders",
            "tone_of_voice": "other",
            "custom_tone": "Candid, sharp and encouraging",
            "negative_guardrails": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            BrandProfile.objects.get(name="Founder Lab").tone_of_voice,
            "Candid, sharp and encouraging",
        )

    def test_new_brand_requires_owner_confirmation_without_duplicate_memory(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:brand_create"), {
            "name": "Luma Skin", "niche": "Lagos skincare",
            "business_model": "d2c_ecommerce",
            "primary_goal": "Generate 30 qualified WhatsApp enquiries in 90 days",
            "weekly_posts_capacity": 3, "conversion_url": "https://example.com/whatsapp",
            "target_audience": "Women aged 20 to 35 in Lagos with oily skin",
            "tone_of_voice": "Calm and reassuring", "custom_tone": "",
            "negative_guardrails": "Do not claim to cure acne.",
            "competitor_notes": "Active Rival | Instagram + TikTok | https://instagram.com/active | https://tiktok.com/@active",
        })
        brand = BrandProfile.objects.get(name="Luma Skin")
        self.assertRedirects(response, reverse("web:brand_confirm", args=[brand.pk]))
        blocked = self.client.post(reverse("web:strategy_generate", args=[brand.pk]), {})
        self.assertRedirects(blocked, reverse("web:brand_confirm", args=[brand.pk]))
        confirmed = self.client.post(reverse("web:brand_confirm", args=[brand.pk]))
        self.assertRedirects(confirmed, reverse("web:brand_detail", args=[brand.pk]))
        brand.refresh_from_db()
        self.assertEqual(brand.strategy_inputs["onboarding_status"], "confirmed")
        self.assertIn("Active Rival", brand.strategy_inputs["competitor_notes"])
        self.assertFalse(brand.memories.filter(source="onboarding").exists())
        self.assertEqual(approved_brand_memory(brand), "No additional confirmed brand memory has been saved.")

    @patch("core.audience_service.generate_with_fallback", side_effect=RuntimeError("AI unavailable"))
    def test_audience_suggestion_has_starter_fallback(self, _generator):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("web:audience_suggestion"),
            data=json.dumps({
                "brand_name": "Example Co", "niche": "local bakery",
                "business_model": "local_business", "primary_goal": "more bookings",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "starter")
        self.assertIn("Likely audience:", payload["suggestion"])
        self.assertIn("What they likely need:", payload["suggestion"])
        self.assertIn("What may get in the way:", payload["suggestion"])

    @patch("core.web_views.analyze_brand_from_url")
    def test_website_scan_accepts_bare_domain_and_normalizes_https(self, analyzer):
        analyzer.return_value = {
            "brand_name": "Luma Skin", "niche": "Skincare",
            "business_model": "d2c_ecommerce", "target_audience": "Women in Lagos",
            "tone_of_voice": "Calm and reassuring",
        }
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:brand_scan"), {"url": "www.lumaskin.com"})
        brand = BrandProfile.objects.get(name="Luma Skin")
        analyzer.assert_called_once_with("https://www.lumaskin.com")
        self.assertEqual(brand.conversion_url, "https://www.lumaskin.com")
        self.assertEqual(brand.strategy_inputs["onboarding_status"], "pending")
        self.assertRedirects(response, reverse("web:brand_confirm", args=[brand.pk]))

    def test_website_scan_field_does_not_block_bare_domains_in_browser(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:brand_scan"))
        self.assertContains(response, 'type="text"', html=False)
        self.assertContains(response, "Sovaro will add https://")

    @patch("core.web_views.analyze_brand_from_url", side_effect=WebsiteFetchError("Website returned HTTP 403.", status_code=403))
    def test_blocked_website_explains_no_ai_model_ran(self, analyzer):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:brand_scan"), {"url": "dove.com"})
        self.assertContains(response, "No AI model ran")
        self.assertContains(response, "add the brand manually")
        analyzer.assert_called_once_with("https://dove.com")

    @patch("core.web_views.discover_active_competitors")
    def test_competitor_search_returns_only_service_verified_candidates(self, discover):
        discover.return_value = {
            "source_status": "grounded", "limitations": [],
            "competitors": [{
                "name": "Active Rival", "relationship": "direct competitor",
                "why_relevant": "Serves the same market.",
                "verification_status": "Recent activity found on at least two social platforms",
                "platforms": [
                    {"platform": "Instagram", "url": "https://instagram.com/active", "recent_posts_found": 3, "recent_activity_evidence": "Recent posts found"},
                    {"platform": "LinkedIn", "url": "https://linkedin.com/company/active", "recent_posts_found": 2, "recent_activity_evidence": "Recent posts found"},
                ],
            }],
        }
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("web:competitor_suggestion"),
            data=json.dumps({"brand_name": "Example", "industry": "Technology", "audience": "Founders"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["competitors"][0]["name"], "Active Rival")
        discover.assert_called_once_with("Example", "Technology", "Founders", "")

    def test_other_user_cannot_view_brand_workspace(self):
        other = User.objects.create_user(username="other@example.com", password="safe-test-password")
        self.client.force_login(other)
        response = self.client.get(reverse("web:brand_detail", args=[self.brand.pk]))
        self.assertEqual(response.status_code, 404)

    def test_brand_memory_is_owned_reviewable_and_prompt_ready(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:brand_memory", args=[self.brand.pk]), {
            "category": "customer_language",
            "statement": "Customers usually describe the problem as setup taking too long.",
            "evidence": "Repeated in five customer enquiries.",
            "status": "needs_confirmation",
        })
        self.assertRedirects(response, reverse("web:brand_memory", args=[self.brand.pk]))
        memory = BrandMemory.objects.get(brand=self.brand)
        self.assertNotIn("setup taking too long", approved_brand_memory(self.brand))

        self.client.post(reverse("web:brand_memory_status", args=[self.brand.pk, memory.pk]), {
            "status": "confirmed",
        })
        memory.refresh_from_db()
        self.assertEqual(memory.status, "confirmed")
        self.assertIn("setup taking too long", approved_brand_memory(self.brand))
        page = self.client.get(reverse("web:brand_memory", args=[self.brand.pk]))
        self.assertContains(page, "Approved for use, not independently verified.")

        other = User.objects.create_user(username="memory-other@example.com", password="safe-test-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("web:brand_memory", args=[self.brand.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("web:brand_memory_delete", args=[self.brand.pk, memory.pk])).status_code,
            404,
        )

    def test_first_month_report_can_be_reviewed_and_exported(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:report_create", args=[self.brand.pk]), {
            "month": "2026-10", "platform": "Instagram", "current_reach": "1250",
            "top_posts": "How we plan a launch | Reel | 800 | 48 | https://example.com/post",
            "competitor_snapshot": "Acme posted two launch videos this month.",
        })
        report = MonthlyReport.objects.get(brand=self.brand)
        self.assertRedirects(response, reverse("web:report_detail", args=[report.pk]))
        self.assertEqual(report.status, "draft")
        self.assertIn("first recorded month", report.executive_summary)
        self.assertEqual(report.scorecard_data["reach"]["change_type"], "no_baseline")
        self.assertEqual(report.content_performance["top_posts"][0]["title"], "How we plan a launch")
        review = self.client.get(reverse("web:report_detail", args=[report.pk]))
        self.assertContains(review, "Acme posted two launch videos")
        self.assertContains(review, "Edit numbers, posts and competitor notes")
        pdf = self.client.get(reverse("web:report_pdf", args=[report.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.client.post(reverse("web:report_edit_data", args=[report.pk]), {
            "month": "2026-10", "platform": "Instagram", "current_reach": "1500",
            "previous_reach": "1250", "top_posts": "How we plan a launch | Reel | 800 | 48 | https://example.com/post",
        })
        report.refresh_from_db()
        self.assertEqual(report.scorecard_data["reach"]["pct_change"], 20.0)
        self.assertNotIn("first recorded month", report.executive_summary)

    def test_report_ready_requires_review_and_other_user_cannot_access(self):
        self.client.force_login(self.user)
        self.client.post(reverse("web:report_create", args=[self.brand.pk]), {
            "month": "2026-10", "platform": "Instagram", "current_link_clicks": "20",
        })
        report = MonthlyReport.objects.get(brand=self.brand)
        edit = self.client.post(reverse("web:report_detail", args=[report.pk]), {
            "executive_summary": "", "what_worked": "Observed 20 clicks.",
            "next_month_plan": "Test a new CTA.", "status": "ready",
        })
        self.assertEqual(edit.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, "draft")
        self.client.post(reverse("web:report_detail", args=[report.pk]), {
            "executive_summary": "We recorded 20 clicks.", "what_worked": "Observed 20 clicks.",
            "next_month_plan": "Test a new CTA.", "status": "ready",
        })
        report.refresh_from_db()
        self.assertEqual(report.status, "ready")
        other = User.objects.create_user(username="another@example.com", password="safe-test-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("web:report_detail", args=[report.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("web:report_pdf", args=[report.pk])).status_code, 404)

    def test_founder_can_save_strategy_evidence(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_brief_save", args=[self.brand.pk]), {
            "brand_stage": "active",
            "goal_metric": "website enquiries", "baseline": "4", "target": "10",
            "deadline": "2027-02-01", "audience_evidence": "Customers ask about setup time",
            "audit_notes": "FAQ posts get replies",
            "customer_keywords": "setup time, monthly price", "budget": "0",
            "competitor_notes": "@acme\n@otherbrand",
        })
        self.assertEqual(response.status_code, 302)
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.strategy_inputs["goal_metric"], "website enquiries")

    @patch("core.web_views.generate_content_strategy")
    def test_free_strategy_needs_no_ai_service(self, ai_generator):
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_generate", args=[self.brand.pk]), {
            "mode": "starter", "platforms": "LinkedIn", "brand_stage": "new",
            "goal_metric": "website enquiries",
            "baseline": "4", "target": "10", "deadline": "2027-02-01",
            "customer_keywords": "setup time, monthly price", "budget": "0",
            "competitor_notes": "@acme\n@otherbrand",
        })
        self.assertEqual(response.status_code, 302)
        ai_generator.assert_not_called()
        strategy = ContentStrategy.objects.get(brand=self.brand)
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.strategy_inputs["goal_metric"], "website enquiries")
        self.assertEqual(len(strategy.strategy_foundation["tactics"]), 4)
        self.assertIn("4 to 10", strategy.strategy_foundation["goal"])
        self.assertIn("setup time", strategy.content_ideas[0]["hook"])
        self.assertEqual(strategy.strategy_foundation["weekly_posts"], 3)
        self.assertEqual(len(strategy.audience_icp_dossier["personas"]), 3)
        self.assertEqual(len(strategy.weekly_plan), 3)
        self.assertEqual(strategy.validation_report["status"], "blocked")
        self.assertIn("new brand with no posts", strategy.strategy_foundation["audit"])
        self.assertIn("Accounts to review: @acme", strategy.strategy_foundation["competitors"])
        self.assertTrue(any("have not been analysed" in item for item in strategy.strategy_foundation["assumptions"]))
        detail = self.client.get(reverse("web:strategy_detail", args=[strategy.pk]))
        self.assertContains(detail, "The numbers that show progress")
        self.assertContains(detail, "EXECUTIVE SUMMARY")
        self.assertContains(detail, "The brand and strategic direction")
        self.assertContains(detail, "CONVERSION JOURNEY")
        self.assertContains(detail, "30-DAY EXECUTION PLAN")
        self.assertContains(detail, "APPENDIX A")
        self.assertContains(detail, "APPENDIX B")
        self.assertContains(detail, "III")
        self.assertContains(detail, "Primary buyer")
        self.assertContains(detail, "Copy strategy")
        self.assertContains(detail, "Print / Save PDF")
        self.assertContains(detail, "EXECUTABLE WEEK ONE")
        self.assertContains(detail, "Record result")

    @patch("core.web_views.research_content_gaps")
    def test_two_week_button_builds_six_post_trial(self, research):
        research.return_value = {"source_status": "research_unavailable", "ideas": [], "content_gaps": []}
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_generate", args=[self.brand.pk]), {
            "mode": "starter", "plan_horizon": "14", "platforms": "Instagram,TikTok",
            "brand_stage": "new", "goal_metric": "website enquiries", "baseline": "4",
            "target": "10", "deadline": "2027-02-01",
        })
        self.assertEqual(response.status_code, 302)
        strategy = ContentStrategy.objects.get(brand=self.brand)
        self.assertEqual(strategy.strategy_foundation["plan_horizon_days"], 14)
        self.assertEqual(len(strategy.strategy_foundation["two_week_plan"]), 6)
        detail = self.client.get(reverse("web:strategy_detail", args=[strategy.pk]))
        self.assertContains(detail, "TWO-WEEK STARTER STRATEGY")
        self.assertContains(detail, "Live competitor research was unavailable")

    def test_post_result_creates_confirmed_learning_memory(self):
        strategy = ContentStrategy.objects.create(
            brand=self.brand, executive_summary="Starting plan", strategy_foundation={"weekly_posts": 1},
            content_pillars=[], platform_playbook=[], content_mix={}, posting_schedule=[],
            content_ideas=[], kpis=[], cta_strategy=[],
            weekly_plan=[{"key": "week-1-1", "hook": "Answer the setup question", "platform": "LinkedIn"}],
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_results", args=[strategy.pk]), {
            "plan_key": "week-1-1", "title": "Answer the setup question", "platform": "LinkedIn",
            "published_on": "2026-11-18", "reach": 500, "views": 0, "saves": 12,
            "shares": 4, "comments": 3, "link_clicks": 8, "enquiries": 2, "sales": 0,
            "observation": "This post earned more saves than our other posts.",
            "lesson": "Repeat practical setup answers with one direct enquiry CTA.",
            "next_action": "repeat",
        })
        self.assertRedirects(response, reverse("web:strategy_results", args=[strategy.pk]))
        self.assertTrue(PostResult.objects.filter(strategy=strategy, plan_key="week-1-1").exists())
        memory = BrandMemory.objects.get(brand=self.brand, source="post_result")
        self.assertEqual(memory.status, "confirmed")
        self.assertIn("Repeat practical setup answers", approved_brand_memory(self.brand))

    def test_requested_cadence_never_exceeds_owner_capacity(self):
        self.brand.strategy_inputs = {"brand_stage": "new", "goal_metric": "enquiries"}
        plan = generate_starter_strategy(self.brand, requested_weekly_posts=5)
        self.assertEqual(plan["strategy_foundation"]["weekly_posts"], 3)
        self.assertIn("will not exceed that limit", plan["posting_schedule"][0]["rationale"])

    def test_strategy_generation_defaults_to_ai_without_showing_a_mode_choice(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:brand_detail", args=[self.brand.pk]))
        self.assertContains(response, 'name="mode"', html=False)
        self.assertContains(response, 'value="ai"', html=False)
        self.assertNotContains(response, "Free starter plan")
        self.assertNotContains(response, "AI assisted plan")

    def test_goal_sentence_is_not_duplicated_when_target_is_already_stated(self):
        self.brand.strategy_inputs = {
            "brand_stage": "new",
            "goal_metric": "Sell at least 20 cars in the next 3 months",
            "target": "20",
            "deadline": "2027-03-03",
        }
        plan = generate_starter_strategy(self.brand)
        goal = plan["strategy_foundation"]["goal"]
        self.assertEqual(goal, "Sell at least 20 cars by 2027-03-03.")
        self.assertNotIn("from to", goal)

    def test_strategy_normalizer_blocks_unsupplied_customer_proof_and_targets(self):
        raw = {
            "content_ideas": [{
                "hook": "How a local nurse found a reliable car",
                "concept": "Show how our customer bought in under 1 hour.",
                "claim_classification": "evidence_backed",
            }],
            "kpis": [
                {"monthly_targets": "Target 15% MoM growth"},
                {"monthly_targets": "Generate 5 high-intent DMs each week and 100 clicks"},
            ],
            "audience_icp_dossier": {},
            "platform_playbook": [{"platform": "Instagram"}, {"platform": "TikTok"}, {"platform": "X"}],
            "posting_schedule": [
                {"platform": "Instagram", "frequency": "3 per week", "rationale": "Engagement is strongest mid-week."},
                {"platform": "TikTok", "frequency": "3 per week"},
            ],
        }
        result = clean_and_normalize_strategy(raw, requested_posts_per_week=3, strategy_inputs={})
        idea = result["content_ideas"][0]
        self.assertEqual(idea["claim_classification"], "evidence_required")
        self.assertEqual(idea["publish_status"], "blocked_pending_evidence")
        self.assertIn("Establish a 30-day baseline", result["kpis"][0]["monthly_targets"])
        self.assertIn("Establish a 30-day baseline", result["kpis"][1]["monthly_targets"])
        self.assertEqual(len(result["audience_icp_dossier"]["personas"]), 3)
        self.assertEqual(len(result["posting_schedule"]), 2)
        self.assertEqual(
            sum(int(slot["frequency"].split()[0]) for slot in result["posting_schedule"]),
            3,
        )
        self.assertTrue(all("total weekly posts" in slot["share_of_total"] for slot in result["posting_schedule"]))

    @patch("core.web_views.generate_content_strategy", return_value={"executive_summary": "Review before sharing."})
    def test_ai_strategy_receives_weekly_post_choice_and_stage(self, ai_generator):
        BrandMemory.objects.create(
            brand=self.brand,
            category="guardrail",
            statement="Never claim guaranteed implementation times.",
            status="confirmed",
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_generate", args=[self.brand.pk]), {
            "mode": "ai", "brand_stage": "new", "goal_metric": "enquiries",
            "posts_per_week": "4",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ai_generator.call_args.kwargs["posts_per_week"], 4)
        self.assertEqual(ai_generator.call_args.kwargs["weekly_posts_capacity"], 3)
        self.assertEqual(ai_generator.call_args.kwargs["strategy_inputs"]["brand_stage"], "new")
        self.assertIn("guaranteed implementation times", ai_generator.call_args.kwargs["brand_memory"])

    @patch("core.web_views.repair_strategy_sections")
    @patch("core.web_views.generate_content_strategy")
    def test_failed_ai_draft_gets_one_repair_attempt(self, generator, repair):
        draft = generate_starter_strategy(self.brand, "LinkedIn", 3)
        draft["_ai_provider"] = "gemini"
        draft["kpis"] = []
        generator.return_value = draft
        fixed = generate_starter_strategy(self.brand, "LinkedIn", 3)
        fixed["_ai_provider"] = "gemini"
        fixed["executive_summary"] = f"{self.brand.name} will answer buyer questions and test LinkedIn content to support its stated goal."
        repair.return_value = fixed
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_generate", args=[self.brand.pk]), {
            "mode": "ai", "platforms": "LinkedIn", "brand_stage": "new", "goal_metric": "enquiries",
        })
        self.assertEqual(response.status_code, 302)
        repair.assert_called_once()
        strategy = ContentStrategy.objects.get(brand=self.brand)
        self.assertTrue(strategy.validation_report["repair_attempted"])
        self.assertTrue(strategy.kpis)

    @patch("core.web_views.research_content_gaps")
    def test_grounded_gap_research_replaces_ideas_and_keeps_evidence(self, researcher):
        strategy = ContentStrategy.objects.create(
            brand=self.brand,
            executive_summary="Starting plan",
            content_pillars=[], platform_playbook=[], content_mix={},
            posting_schedule=[], content_ideas=[{"hook": "Old idea"}],
            kpis=[], cta_strategy=[],
        )
        researcher.return_value = {
            "research_summary": "Competitors repeat setup guides but rarely cover operational trade-offs.",
            "content_gaps": [{
                "gap": "Operational trade-offs", "why_it_matters": "Helps buyers decide",
                "evidence": "Visible results focus on setup", "source_url": "https://example.com/post",
                "confidence": "medium",
            }],
            "ideas": [{
                "platform": "LinkedIn", "format": "Carousel", "hook": "The hidden trade-off",
                "concept": "Compare two approaches", "gap": "Operational trade-offs",
                "confidence": "medium", "source_url": "https://example.com/post",
            }],
            "queries": ["site:linkedin.com/posts example"],
            "grounding_sources": [{"title": "Example", "url": "https://example.com/post"}],
            "limitations": ["Search results are not the full platform feed."],
            "method": "Google Search grounded research",
        }
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:research_content_gaps", args=[self.brand.pk]))
        self.assertRedirects(response, reverse("web:ideas", args=[self.brand.pk]))
        strategy.refresh_from_db()
        self.assertEqual(strategy.content_ideas[0]["hook"], "The hidden trade-off")
        self.assertEqual(strategy.content_gap_research["content_gaps"][0]["gap"], "Operational trade-offs")
        self.assertIsNotNone(strategy.content_gap_researched_at)

    @patch("core.content_gap_service.get_gemini_client", side_effect=ValueError("missing key"))
    def test_content_gap_research_stops_without_inventing_gaps_or_ideas(self, _client):
        research = research_content_gaps(self.brand)

        self.assertEqual(research["source_status"], "research_unavailable")
        self.assertEqual(research["ideas"], [])
        self.assertEqual(research["content_gaps"], [])
        self.assertEqual(research["grounding_sources"], [])
        self.assertIn("competitor post", " ".join(research["required_inputs"]).lower())

    @patch("core.web_views.research_content_gaps")
    def test_failed_research_removes_retired_generic_fallback_ideas(self, researcher):
        strategy = ContentStrategy.objects.create(
            brand=self.brand, executive_summary="Starting plan",
            content_pillars=[], platform_playbook=[], content_mix={}, posting_schedule=[],
            content_ideas=[{"hook": "Before you choose, ask these questions"}],
            content_gap_research={"source_status": "starter_fallback"},
            kpis=[], cta_strategy=[],
        )
        researcher.return_value = {
            "source_status": "research_unavailable", "content_gaps": [], "ideas": [],
            "research_summary": "No research completed.", "required_inputs": [],
            "limitations": ["No sources inspected."], "queries": [], "grounding_sources": [],
        }
        self.client.force_login(self.user)
        self.client.post(reverse("web:research_content_gaps", args=[self.brand.pk]))
        strategy.refresh_from_db()
        self.assertEqual(strategy.content_ideas, [])

    @patch("core.web_views.analyze_caption")
    def test_caption_coach_is_marked_coming_soon_without_running_ai(self, analyzer):
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:caption_analyzer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CAPTION COACH")
        self.assertContains(response, "COMING SOON")
        self.assertContains(response, "Better feedback is being coached")
        post_response = self.client.post(reverse("web:caption_analyzer"), {
            "platform": "linkedin",
            "caption": "Most teams do not have a content problem. They have a clarity problem.",
        })
        self.assertEqual(post_response.status_code, 200)
        analyzer.assert_not_called()

    @patch("core.web_views.optimize_profile")
    def test_profile_optimizer_returns_copy_ready_profile(self, optimizer):
        optimizer.return_value = {
            "analysis_mode": "ai_optimizer", "summary": "The offer is clear but the next step is buried.",
            "scorecard": {"clarity": 4, "discoverability": 3, "audience_fit": 4, "credibility": 3, "conversion": 2},
            "what_works": ["Clear audience"], "gaps": ["No direct CTA"],
            "keyword_opportunities": ["operations software"],
            "optimized_profile": {"name_field": "Example Co | Operations Software", "bio": "Simplify daily operations.", "cta": "Book a demo"},
            "alternatives": [{"angle": "Outcome-led", "bio": "Spend less time on manual operations."}],
            "action_plan": ["Update the name field"],
            "limitations": "No live analytics were inspected.",
        }
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:profile_optimizer"), {
            "platform": "linkedin", "business_name": "Example Co", "industry": "B2B SaaS",
            "audience": "Operations leaders", "offer": "Operations software", "current_name": "Example Co",
            "current_bio": "We make software for operations teams.",
            "destination": "Book a demo", "profile_goal": "leads", "desired_cta": "Book a demo",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Example Co | Operations Software")
        optimizer.assert_called_once()

    @patch("core.web_views.optimize_profile")
    def test_profile_optimizer_accepts_a_brand_without_a_current_bio(self, optimizer):
        optimizer.return_value = {
            "analysis_mode": "ai_optimizer", "starting_from_scratch": True,
            "summary": "A first profile foundation was created.",
            "scorecard": {"clarity": 3, "discoverability": 3, "audience_fit": 4, "credibility": 2, "conversion": 3},
            "what_works": [], "gaps": ["Add a clear audience and next step"],
            "keyword_opportunities": ["operations software"],
            "optimized_profile": {"name_field": "Example Co", "bio": "Operations software for growing teams.", "cta": "Book a demo"},
            "alternatives": [], "action_plan": ["Publish the first bio"],
            "limitations": "No live analytics were inspected.",
        }
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:profile_optimizer"), {
            "platform": "instagram", "business_name": "Example Co", "industry": "B2B SaaS",
            "audience": "Operations leaders", "current_name": "Example Co", "current_bio": "",
            "destination": "Book a demo", "profile_goal": "leads",
            "offer": "Operations software", "desired_cta": "Book a demo",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations software for growing teams")
        optimizer.assert_called_once()

    def test_owner_can_remove_a_brand_from_the_dashboard(self):
        brand_pk = self.brand.pk
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:brand_delete", args=[brand_pk]))
        self.assertRedirects(response, reverse("web:dashboard"))
        self.assertFalse(BrandProfile.objects.filter(pk=brand_pk).exists())

    def test_profile_optimizer_is_available_without_a_saved_brand(self):
        standalone_user = User.objects.create_user(username="solo@example.com", password="safe-test-password")
        self.client.force_login(standalone_user)
        response = self.client.get(reverse("web:profile_optimizer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No saved brand needed")

    def test_profile_optimizer_offers_saved_brand_prefill(self):
        self.brand.strategy_inputs = {
            "offer_details": "Operations software for small teams",
            "differentiators": "Simple setup",
            "service_area": "United Kingdom",
            "proof_available": "Owner says the product is already used by two teams",
        }
        self.brand.tone_of_voice = "Clear and practical"
        self.brand.primary_goal = "Generate 10 qualified enquiries"
        self.brand.negative_guardrails = "Do not promise guaranteed savings"
        self.brand.social_profiles = {"linkedin": "https://www.linkedin.com/company/example-co/"}
        self.brand.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:profile_optimizer") + f"?brand={self.brand.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use a saved brand")
        self.assertContains(response, self.brand.name)
        self.assertContains(response, self.brand.target_audience)
        self.assertEqual(response.context["form"]["saved_brand"].value(), str(self.brand.pk))
        self.assertEqual(response.context["form"]["offer"].value(), "Operations software for small teams")
        self.assertEqual(response.context["form"]["brand_voice"].value(), "Clear and practical")
        self.assertEqual(response.context["form"]["claims_to_avoid"].value(), "Do not promise guaranteed savings")
        self.assertEqual(response.context["form"]["platform"].value(), "linkedin")
        self.assertEqual(response.context["form"]["profile_reference"].value(), "https://www.linkedin.com/company/example-co/")
        self.assertFalse(response.context["form"]["current_bio"].value())
        self.assertEqual(response.context["form"]["desired_cta"].value(), "Send an enquiry")

    def test_profile_cta_follows_goal_and_known_destination(self):
        self.assertEqual(suggest_profile_cta("leads", "Get 20 enquiries", "https://wa.me/234123"), "Message us on WhatsApp to enquire")
        self.assertEqual(suggest_profile_cta("leads", "Get 10 bookings"), "Ask about booking an appointment")
        self.assertEqual(suggest_profile_cta("sales", "Sell more products"), "Explore the offer")

    @patch("core.web_views.generate_repurpose_package")
    def test_repurpose_studio_saves_selected_platform_drafts(self, generator):
        generator.return_value = {
            "source_analysis": {"central_thesis": "Consistency should match capacity."},
            "hook_options": [{"hook": "Posting daily is not the goal.", "total": 26}],
            "outputs": [
                {"platform": "LinkedIn", "format": "Text post", "hook": "A better cadence", "body": "Useful body", "caption": "", "cta": "Reply", "visual_direction": "None"},
                {"platform": "Instagram", "format": "Carousel", "hook": "Post less, learn more", "body": "Slides", "caption": "Useful caption", "cta": "Save", "visual_direction": "Five slides"},
            ],
            "quality_report": {"status": "clean_draft", "warnings": []},
        }
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:repurpose_studio", args=[self.brand.pk]), {
            "mode": "fresh",
            "source_title": "Sustainable posting",
            "source_content": "Small brands should choose a posting pace they can sustain.",
            "platforms": ["linkedin", "instagram"],
            "objective": "authority",
            "desired_action": "Reply with their current posting pace",
        })
        project = RepurposeProject.objects.get(brand=self.brand)
        self.assertRedirects(response, reverse("web:repurpose_detail", args=[project.pk]))
        self.assertEqual(project.platforms, ["linkedin", "instagram"])
        self.assertEqual(len(project.outputs), 2)
        self.assertContains(self.client.get(reverse("web:repurpose_detail", args=[project.pk])), "PLATFORM DRAFTS")

    def test_other_user_cannot_open_repurpose_project(self):
        project = RepurposeProject.objects.create(
            brand=self.brand, mode="fresh", source_content="A useful idea",
            platforms=["linkedin"], objective="authority",
        )
        other = User.objects.create_user(username="repurpose-other@example.com", password="safe-test-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("web:repurpose_detail", args=[project.pk])).status_code, 404)
