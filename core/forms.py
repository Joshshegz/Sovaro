from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import BrandMemory, BrandProfile, MonthlyReport, PostResult


REPORT_METRICS = (
    ("reach", "Reach"), ("impressions", "Views or impressions"),
    ("engagements", "Engagements"), ("engagement_rate", "Engagement rate (%)"),
    ("followers_total", "Followers at month end"), ("link_clicks", "Link clicks"),
    ("conversions", "Enquiries or sales"), ("posts_count", "Posts published"),
)


class ReportInputForm(forms.Form):
    month = forms.DateField(label="Reporting month", widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"), input_formats=["%Y-%m", "%Y-%m-%d"])
    platform = forms.CharField(max_length=100, label="Platform(s)", help_text="For example: Instagram, TikTok")
    csv_file = forms.FileField(required=False, label="Post results CSV", help_text="Optional. Include title, platform, format, impressions or reach, and engagements. Maximum 2 MB.")
    top_posts = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Top posts", help_text="Optional if uploading a post CSV. One per line: title | format | impressions | engagements | link")
    competitor_snapshot = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Competitor snapshot", help_text="Optional. Name one or two brands and what you observed this month. No claims about their results unless you have the numbers.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in REPORT_METRICS:
            self.fields[f"current_{key}"] = forms.DecimalField(required=False, min_value=0, decimal_places=2, label=f"This month: {label}")
            self.fields[f"previous_{key}"] = forms.DecimalField(required=False, min_value=0, decimal_places=2, label=f"Last month: {label}")

    def clean_csv_file(self):
        upload = self.cleaned_data.get("csv_file")
        if upload and (upload.size > 2 * 1024 * 1024 or not upload.name.lower().endswith(".csv")):
            raise forms.ValidationError("Upload a CSV file smaller than 2 MB.")
        return upload

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("csv_file") and not any(cleaned.get(f"current_{key}") is not None for key, _ in REPORT_METRICS):
            raise forms.ValidationError("Add at least one result for this month or upload a CSV.")
        return cleaned


class ReportReviewForm(forms.ModelForm):
    class Meta:
        model = MonthlyReport
        fields = ("executive_summary", "what_worked", "competitor_snapshot", "next_month_plan", "status")
        widgets = {key: forms.Textarea(attrs={"rows": 5}) for key in ("executive_summary", "what_worked", "competitor_snapshot", "next_month_plan")}
        labels = {"executive_summary": "Summary", "what_worked": "What worked and what didn't", "competitor_snapshot": "Competitor snapshot", "next_month_plan": "Next month's plan", "status": "Report status"}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == "ready" and not all(cleaned.get(key, "").strip() for key in ("executive_summary", "what_worked", "next_month_plan")):
            raise forms.ValidationError("Complete the summary, learning, and next-month plan before marking the report ready.")
        if cleaned.get("status") == "ready" and ("Hypothesis to check:" in cleaned.get("what_worked", "") or "Add a post example" in cleaned.get("what_worked", "") or cleaned.get("next_month_plan", "").startswith("Choose one theme")):
            raise forms.ValidationError("Replace the draft prompts with your own learning and concrete next-month plan before marking the report ready.")
        return cleaned


class PostResultForm(forms.ModelForm):
    class Meta:
        model = PostResult
        fields = (
            "plan_key", "title", "platform", "published_on", "reach", "views",
            "saves", "shares", "comments", "link_clicks", "enquiries", "sales",
            "observation", "lesson", "next_action",
        )
        widgets = {
            "plan_key": forms.HiddenInput(),
            "published_on": forms.DateInput(attrs={"type": "date"}),
            "observation": forms.Textarea(attrs={"rows": 3, "placeholder": "What happened? State only what the numbers or responses show."}),
            "lesson": forms.Textarea(attrs={"rows": 3, "placeholder": "What should the next post do differently?"}),
        }
        labels = {
            "title": "Post or content title",
            "published_on": "Date published",
            "reach": "Reach",
            "views": "Views",
            "link_clicks": "Link clicks",
            "enquiries": "Qualified enquiries",
            "sales": "Sales attributed",
            "observation": "What did you observe?",
            "lesson": "What did you learn?",
            "next_action": "What should happen next?",
        }

    def clean(self):
        cleaned = super().clean()
        metrics = ("reach", "views", "saves", "shares", "comments", "link_clicks", "enquiries", "sales")
        if not any(cleaned.get(metric) for metric in metrics) and not (cleaned.get("observation") or "").strip():
            raise forms.ValidationError("Add at least one result or a clear observation from the post.")
        if cleaned.get("next_action") != "insufficient" and not (cleaned.get("lesson") or "").strip():
            self.add_error("lesson", "Add the evidence-based lesson behind this decision.")
        return cleaned


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="First name")
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ("first_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs.update({"placeholder": "Ada", "autocomplete": "given-name", "autofocus": True})
        self.fields["email"].widget.attrs.update({"placeholder": "ada@company.com", "autocomplete": "email"})
        self.fields["password1"].widget.attrs.update({"placeholder": "Create a secure password", "autocomplete": "new-password"})
        self.fields["password2"].widget.attrs.update({"placeholder": "Enter the password again", "autocomplete": "new-password"})

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"].strip()
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email address")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"placeholder": "you@company.com", "autocomplete": "email", "autofocus": True})
        self.fields["password"].widget.attrs.update({"placeholder": "Your password", "autocomplete": "current-password"})


class AccountSettingsForm(forms.ModelForm):
    email = forms.EmailField(label="Email address")

    class Meta:
        model = User
        fields = ("first_name", "email")
        labels = {"first_name": "Display name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs.update({"autocomplete": "name", "placeholder": "Your name"})
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "placeholder": "you@company.com"})

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        if commit:
            user.save()
        return user


class BrandForm(forms.ModelForm):
    TONE_CHOICES = (
        ("", "Choose a brand tone"),
        ("Warm and approachable", "Warm & approachable — friendly and human"),
        ("Professional and trustworthy", "Professional & trustworthy — credible and polished"),
        ("Clear and educational", "Clear & educational — useful and easy to understand"),
        ("Playful and energetic", "Playful & energetic — lively, fun and informal"),
        ("Bold and confident", "Bold & confident — direct and opinionated"),
        ("Calm and reassuring", "Calm & reassuring — supportive and steady"),
        ("Luxurious and refined", "Luxurious & refined — elegant and aspirational"),
        ("other", "Other / create a custom tone"),
    )

    business_model = forms.ChoiceField(
        label="How does your business make money?",
        choices=(
            ("b2b_saas", "Software sold to businesses"),
            ("d2c_ecommerce", "Online shop"),
            ("professional_services", "Professional services"),
            ("local_business", "Local business"),
            ("agency", "Agency"),
            ("other", "Other"),
        ),
    )
    primary_goal = forms.CharField(
        required=True,
        label="Main business goal",
        help_text="State the result the business needs from social media. This must come from the brand owner.",
        widget=forms.TextInput(attrs={"placeholder": "For example: generate 20 qualified enquiries each month"}),
    )
    weekly_posts_capacity = forms.TypedChoiceField(
        coerce=int,
        label="How many times can you realistically post each week?",
        choices=((1, "Once a week"), (2, "2 times a week"), (3, "3 times a week"),
                 (4, "4 times a week"), (5, "5 times a week"), (6, "6 times a week"),
                 (7, "Every day")),
        help_text="Choose a pace you can maintain. The strategy will not recommend more than this.",
    )
    tone_of_voice = forms.ChoiceField(
        label="How should your brand sound?",
        choices=TONE_CHOICES,
        help_text="Choose the closest fit. You can create your own tone if none feels right.",
    )
    custom_tone = forms.CharField(
        required=False,
        label="Describe your custom brand tone",
        help_text="Use two or three words, such as: witty, honest and encouraging.",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "For example: witty, honest and encouraging"}),
    )
    competitor_notes = forms.CharField(
        required=False,
        label="Active competitors",
        help_text="Optional. Add competitors you know, or ask Sovaro to find brands with recent activity on at least two social platforms.",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "One competitor per line, with profile links when possible"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "name": "For example: Ada's Cakes",
            "niche": "For example: Technology, Logistics, E-commerce or Skincare",
            "target_audience": "For example: Lagos founders building their first online business",
            "negative_guardrails": "Claims, topics or promises the brand should avoid",
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = placeholder
        self.fields["name"].widget.attrs["autofocus"] = True
        self.fields["niche"].label = "Industry"
        self.fields["niche"].help_text = "Use a short category, usually one to three words. Describe the business elsewhere."
        self.fields["target_audience"].help_text = "Keep this short: who they are, plus location or life stage when relevant. Needs and barriers are captured in the strategy brief."

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("tone_of_voice") == "other":
            custom_tone = (cleaned_data.get("custom_tone") or "").strip()
            if not custom_tone:
                self.add_error("custom_tone", "Describe how you want the brand to sound.")
            else:
                cleaned_data["tone_of_voice"] = custom_tone
        return cleaned_data

    class Meta:
        model = BrandProfile
        fields = (
            "name", "niche", "business_model", "primary_goal",
            "weekly_posts_capacity", "conversion_url", "target_audience",
            "tone_of_voice", "custom_tone", "negative_guardrails", "competitor_notes",
        )
        widgets = {
            "target_audience": forms.Textarea(attrs={"rows": 4}),
            "negative_guardrails": forms.Textarea(attrs={"rows": 3}),
            "conversion_url": forms.URLInput(attrs={"placeholder": "https://example.com"}),
        }
        labels = {
            "name": "Brand or business name",
            "niche": "Industry",
            "business_model": "How does your business make money?",
            "primary_goal": "Main business goal",
            "weekly_posts_capacity": "How many times can you realistically post each week?",
            "conversion_url": "Where should interested people go?",
            "target_audience": "Who do you want to reach?",
            "tone_of_voice": "How should your brand sound?",
            "negative_guardrails": "Topics or claims to avoid",
        }
        help_texts = {
            "niche": "Use a short category such as Technology, Logistics, E-commerce, Education, or Skincare.",
            "business_model": "For example: online shop, local service, or subscription product.",
            "conversion_url": "A website, shop, booking page, or contact link. Optional.",
            "target_audience": "Describe the people most likely to buy from you and what they need.",
            "negative_guardrails": "Anything your posts should never promise or discuss.",
        }


class BrandProfileForm(forms.ModelForm):
    class Meta:
        model = BrandProfile
        fields = ("brand_image",)
        labels = {"brand_image": "Brand image or logo"}
        help_texts = {"brand_image": "Upload a square PNG, JPG, WEBP or GIF. Maximum 3 MB."}
        widgets = {"brand_image": forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg,image/webp,image/gif"})}

    def clean_brand_image(self):
        image = self.cleaned_data.get("brand_image")
        if image and image.size > 3 * 1024 * 1024:
            raise forms.ValidationError("Choose an image smaller than 3 MB.")
        return image


class BrandDetailsForm(forms.ModelForm):
    class Meta:
        model = BrandProfile
        fields = ("name", "niche", "primary_goal", "target_audience", "tone_of_voice", "weekly_posts_capacity", "conversion_url", "negative_guardrails")
        labels = {"name": "Brand name", "niche": "Industry", "primary_goal": "Business goal", "target_audience": "Audience", "tone_of_voice": "Brand voice", "weekly_posts_capacity": "Posts per week in total", "conversion_url": "Where interested people go", "negative_guardrails": "Claims or topics to avoid"}
        widgets = {"target_audience": forms.Textarea(attrs={"rows": 2}), "negative_guardrails": forms.Textarea(attrs={"rows": 2})}


class BrandMemoryForm(forms.ModelForm):
    class Meta:
        model = BrandMemory
        fields = ("category", "statement", "evidence", "status")
        labels = {
            "category": "What kind of knowledge is this?",
            "statement": "What should Sovaro remember?",
            "evidence": "What supports this?",
            "status": "How certain is this?",
        }
        help_texts = {
            "statement": "Write one clear fact, insight, lesson or restriction.",
            "evidence": "Optional: customer quote, report result, owner confirmation or source note.",
            "status": "Only confirmed memories are used as facts in AI outputs.",
        }
        widgets = {
            "statement": forms.Textarea(attrs={"rows": 3, "placeholder": "For example: Customers usually ask about delivery time before price."}),
            "evidence": forms.Textarea(attrs={"rows": 2, "placeholder": "For example: Repeated in five customer enquiries this month."}),
        }

    def clean_statement(self):
        statement = self.cleaned_data["statement"].strip()
        if len(statement) < 10:
            raise forms.ValidationError("Add enough detail for this memory to be useful.")
        return statement


class StrategyOptionsForm(forms.Form):
    mode = forms.ChoiceField(
        choices=(("starter", "Free starter plan"), ("ai", "AI assisted plan")),
        initial="ai",
        widget=forms.HiddenInput(),
    )
    platforms = forms.CharField(
        required=False,
        label="Social platforms to focus on",
        help_text="Optional. Enter names separated by commas, such as Instagram, LinkedIn.",
    )
    posts_per_week = forms.IntegerField(
        required=False, min_value=1, max_value=14,
        label="Posts per week, if you already have a target",
        help_text="Optional. Leave blank to use the sustainable weekly pace the brand owner selected.",
    )


class StrategyBriefForm(forms.Form):
    brand_stage = forms.ChoiceField(
        choices=(("unknown", "Not sure yet"), ("new", "New brand or starting from scratch"), ("active", "Already posting")),
        initial="unknown", label="Where is this brand starting?",
    )
    service_area = forms.CharField(
        required=False,
        label="Where do you sell or serve customers?",
        help_text="Add the city, country, delivery area, or say online worldwide.",
        widget=forms.TextInput(attrs={"placeholder": "For example: Lagos and nearby areas"}),
    )
    offer_details = forms.CharField(
        required=False,
        label="What exactly are you trying to sell?",
        help_text="Describe the main products, services, inventory, or package this strategy should support.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "For example: inspected used cars between ₦8m and ₦20m"}),
    )
    price_range = forms.CharField(
        required=False,
        label="Typical price range",
        help_text="Optional. This helps Sovaro avoid targeting people who cannot realistically buy.",
        widget=forms.TextInput(attrs={"placeholder": "For example: ₦8m–₦20m"}),
    )
    differentiators = forms.CharField(
        required=False,
        label="Why do customers choose you?",
        help_text="Only include differences you can honestly prove.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "For example: same-day delivery, verified service history, specialist experience"}),
    )
    proof_available = forms.CharField(
        required=False,
        label="What proof can the content use?",
        help_text="Add real reviews, results, records, demonstrations, credentials, or customer stories you have permission to share.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Leave blank if no proof is ready yet"}),
    )
    goal_metric = forms.CharField(required=False, label="How will you measure progress?", help_text="Optional if your business goal already names the result, such as enquiries or sales.")
    baseline = forms.DecimalField(required=False, min_value=0, label="Current result", help_text="Leave blank if you have not measured it yet.")
    target = forms.DecimalField(required=False, min_value=0, label="Target result")
    deadline = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Target date")
    audience_evidence = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="What are customers telling you?", help_text="Add questions or feedback you've heard. Leave blank if you are just starting.")
    audit_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="What has worked in your past posts?", help_text="Include what did not work, too. This is your quick social media audit.")
    competitor_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Brand name, @handle, or link — one per line"}),
        label="Similar brands to review",
        help_text="Optional. Paste up to five names, handles, or links. No analysis or long description needed.",
    )
    customer_keywords = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="What words do customers use?", help_text="Add a few phrases, separated by commas.")
    budget = forms.DecimalField(
        required=False,
        min_value=0,
        initial=0,
        label="Monthly ads budget",
        help_text="How much can you spend on paid social ads each month? Enter 0 if you plan to grow organically.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("baseline") is not None and cleaned.get("target") is not None:
            if cleaned["target"] <= cleaned["baseline"]:
                self.add_error("target", "Set a target above your current result, or leave it blank until you know your starting point.")
        return cleaned


class RepurposeForm(forms.Form):
    MODE_CHOICES = (
        ("repurpose", "Repurpose existing content"),
        ("fresh", "Start from a rough idea"),
    )
    PLATFORM_CHOICES = (
        ("linkedin", "LinkedIn"),
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("x", "X"),
        ("threads", "Threads"),
    )
    OBJECTIVE_CHOICES = (
        ("authority", "Build authority"),
        ("engagement", "Start conversations"),
        ("awareness", "Reach new people"),
        ("leads", "Generate enquiries"),
        ("sales", "Support sales"),
    )

    mode = forms.ChoiceField(choices=MODE_CHOICES, widget=forms.RadioSelect, initial="repurpose", label="How do you want to start?")
    source_title = forms.CharField(required=False, max_length=255, label="Working title", widget=forms.TextInput(attrs={"placeholder": "For example: Why our onboarding process changed"}))
    source_content = forms.CharField(
        label="Source content or rough idea",
        widget=forms.Textarea(attrs={"rows": 11, "placeholder": "Paste an article, transcript, newsletter, post, notes—or type one or two rough thoughts."}),
        help_text="Sovaro will preserve your meaning and flag anything it cannot support from this source.",
    )
    platforms = forms.MultipleChoiceField(choices=PLATFORM_CHOICES, widget=forms.CheckboxSelectMultiple, label="Repurpose for")
    objective = forms.ChoiceField(choices=OBJECTIVE_CHOICES, label="What should this content achieve?")
    desired_action = forms.CharField(required=False, max_length=255, label="What should people do next?", widget=forms.TextInput(attrs={"placeholder": "For example: reply with their biggest challenge"}))

    def clean_source_content(self):
        content = self.cleaned_data["source_content"].strip()
        mode = self.data.get("mode", "repurpose")
        minimum = 8 if mode == "fresh" else 40
        if len(content) < minimum:
            raise forms.ValidationError(
                "Add at least one clear thought." if mode == "fresh" else "Paste a little more source material so the output stays faithful."
            )
        return content

    def clean_platforms(self):
        platforms = self.cleaned_data["platforms"]
        if len(platforms) > 5:
            raise forms.ValidationError("Choose up to five platforms.")
        return platforms


class CaptionAnalyzerForm(forms.Form):
    PLATFORM_CHOICES = (
        ("linkedin", "LinkedIn"), ("instagram", "Instagram"),
        ("tiktok", "TikTok"), ("x", "X"), ("threads", "Threads"),
        ("other", "Other / not sure"),
    )
    platform = forms.ChoiceField(choices=PLATFORM_CHOICES, label="Where was this published?")
    caption = forms.CharField(
        label="Caption or social post",
        widget=forms.Textarea(attrs={"rows": 13, "placeholder": "Paste the complete caption or post here…"}),
        help_text="Paste the words exactly as they appeared, including the opening line and call to action.",
    )
    performance_context = forms.CharField(
        required=False,
        label="What happened after it was published?",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Optional: 18,000 impressions, 240 likes, 63 comments, 41 saves, 22 link clicks…"}),
        help_text="Add real results if you have them. Without metrics, Sovaro will assess potential—not claim the post performed well.",
    )

    def clean_caption(self):
        caption = self.cleaned_data["caption"].strip()
        if len(caption) < 20:
            raise forms.ValidationError("Paste at least a few complete sentences so Sovaro can explain the writing choices.")
        if len(caption) > 12000:
            raise forms.ValidationError("Keep the pasted content below 12,000 characters.")
        return caption


class ProfileOptimizerForm(forms.Form):
    PLATFORM_CHOICES = (
        ("instagram", "Instagram"), ("tiktok", "TikTok"),
        ("linkedin", "LinkedIn"), ("x", "X"), ("youtube", "YouTube"),
    )
    GOAL_CHOICES = (
        ("discovery", "Help the right people find the profile"),
        ("leads", "Generate enquiries or bookings"),
        ("sales", "Drive product or service sales"),
        ("authority", "Build authority and trust"),
        ("community", "Grow an engaged community"),
    )
    saved_brand = forms.ChoiceField(required=False, choices=(("", "Start from scratch"),), label="Use a saved brand")
    platform = forms.ChoiceField(choices=PLATFORM_CHOICES, label="Platform")
    profile_reference = forms.CharField(
        required=False, max_length=300, label="Profile username or URL",
        widget=forms.TextInput(attrs={"placeholder": "Optional - for example: @yourbrand"}),
        help_text="Used as context only. Sovaro does not claim to inspect the live profile.",
    )
    business_name = forms.CharField(max_length=120, label="Business or creator name", widget=forms.TextInput(attrs={"placeholder": "For example: Dovee"}))
    industry = forms.CharField(max_length=180, label="What industry or category are you in?", widget=forms.TextInput(attrs={"placeholder": "For example: creator marketplace or Lagos bakery"}))
    audience = forms.CharField(max_length=300, label="Who do you want to attract?", widget=forms.TextInput(attrs={"placeholder": "Describe the customers, clients, followers or partners you want"}))
    current_name = forms.CharField(required=False, max_length=120, label="Current profile name", widget=forms.TextInput(attrs={"placeholder": "Optional—leave blank if the profile is new"}))
    current_bio = forms.CharField(required=False, label="Current bio or About text", widget=forms.Textarea(attrs={"rows": 6, "placeholder": "Paste the current bio—or leave this blank to create one from scratch."}), help_text="Optional. Leave blank if the profile is new or has no bio yet.")
    profile_category = forms.CharField(required=False, max_length=120, label="Current profile category", widget=forms.TextInput(attrs={"placeholder": "Optional - for example: Beauty, Consultant, Software"}))
    destination = forms.CharField(required=False, max_length=300, label="Where should visitors go next?", widget=forms.TextInput(attrs={"placeholder": "Website, booking page, shop, newsletter or DMs"}))
    profile_goal = forms.ChoiceField(choices=GOAL_CHOICES, label="What should this profile achieve?")
    offer = forms.CharField(max_length=300, label="What do you offer?", widget=forms.TextInput(attrs={"placeholder": "The product, service or transformation people can get"}))
    differentiator = forms.CharField(required=False, max_length=300, label="Why should someone choose this brand?", widget=forms.TextInput(attrs={"placeholder": "A specific approach, advantage or point of view"}))
    service_area = forms.CharField(required=False, max_length=180, label="Where do you serve?", widget=forms.TextInput(attrs={"placeholder": "For example: Lagos, worldwide, or remote"}))
    proof_points = forms.CharField(required=False, max_length=400, label="What can build trust?", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional: verified experience, credentials, customer type or genuine proof"}))
    brand_voice = forms.CharField(required=False, max_length=255, label="How should this sound?", widget=forms.TextInput(attrs={"placeholder": "For example: clear and reassuring"}))
    claims_to_avoid = forms.CharField(required=False, label="Claims or topics to avoid", widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional: promises the brand cannot make"}))
    desired_cta = forms.CharField(max_length=180, label="What should a visitor do next?", help_text="Sovaro suggests one action from your goal. Edit it to match how people can actually contact or buy from you.", widget=forms.TextInput(attrs={"placeholder": "For example: ask about booking or explore the offer"}))

    def __init__(self, *args, brands=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["saved_brand"].choices = [("", "Start from scratch")] + [
            (str(brand.pk), brand.name) for brand in (brands or [])
        ]

    def clean_current_bio(self):
        return self.cleaned_data["current_bio"].strip()
