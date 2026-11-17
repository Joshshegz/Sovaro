import json
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from .models import BrandProfile, ContentStrategy, MonthlyReport, RepurposeProject
from .content_gap_service import research_content_gaps
from .ai_service import clean_and_normalize_strategy
from .strategy_service import generate_starter_strategy


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

    def test_other_user_cannot_view_brand_workspace(self):
        other = User.objects.create_user(username="other@example.com", password="safe-test-password")
        self.client.force_login(other)
        response = self.client.get(reverse("web:brand_detail", args=[self.brand.pk]))
        self.assertEqual(response.status_code, 404)

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
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:strategy_generate", args=[self.brand.pk]), {
            "mode": "ai", "brand_stage": "new", "goal_metric": "enquiries",
            "posts_per_week": "4",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ai_generator.call_args.kwargs["posts_per_week"], 4)
        self.assertEqual(ai_generator.call_args.kwargs["weekly_posts_capacity"], 3)
        self.assertEqual(ai_generator.call_args.kwargs["strategy_inputs"]["brand_stage"], "new")

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
    def test_content_gap_research_falls_back_without_claiming_live_sources(self, _client):
        research = research_content_gaps(self.brand)

        self.assertEqual(research["source_status"], "starter_fallback")
        self.assertEqual(len(research["ideas"]), 12)
        self.assertEqual(research["grounding_sources"], [])
        self.assertTrue(all(gap["confidence"] == "low" for gap in research["content_gaps"]))
        self.assertIn("no live web search", research["method"].lower())

    @patch("core.web_views.analyze_caption")
    def test_caption_analyzer_teaches_without_claiming_unproven_performance(self, analyzer):
        analyzer.return_value = {
            "analysis_mode": "ai_coach", "verdict_label": "Potential effectiveness review",
            "summary": "The opening creates useful tension.", "purpose": "Teach a practical lesson.",
            "hook": {"type": "Contrarian", "why_it_may_work": "It challenges an assumption.", "risk": "The body must prove it."},
            "strengths": ["Specific opening"], "weaknesses": ["CTA is broad"],
            "improvements": ["Ask one direct question"],
            "scorecard": {"hook": 4, "clarity": 4, "relevance": 3, "credibility": 3, "cta": 2},
            "platform_fit": "Appropriate for LinkedIn.",
            "performance_interpretation": "No metrics were supplied, so this does not prove performance.",
            "rewrite": "A sharper rewritten post.", "rewrite_notes": ["Made the CTA specific."],
        }
        self.client.force_login(self.user)
        response = self.client.post(reverse("web:caption_analyzer"), {
            "platform": "linkedin",
            "caption": "Most teams do not have a content problem. They have a clarity problem.",
            "performance_context": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Potential effectiveness review")
        self.assertContains(response, "does not prove performance")
        analyzer.assert_called_once()
        self.assertIsNone(analyzer.call_args.args[0])

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
        self.client.force_login(self.user)
        response = self.client.get(reverse("web:profile_optimizer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use a saved brand")
        self.assertContains(response, self.brand.name)
        self.assertContains(response, self.brand.target_audience)

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
