/**
 * DocuFlow Onboarding Flow
 * Handles multi-step organization creation with professional UX
 */

let currentStep = 1;
const totalSteps = 3;

// Form data storage
const onboardingData = {
    orgName: '',
    userEmail: '',  // From OAuth
    plan: 'trial'
};

/**
 * Initialize onboarding flow
 */
async function initOnboarding() {
    // Check if user is authenticated
    const authenticated = await isAuthenticated();
    if (!authenticated) {
        window.location.href = '/login.html';
        return;
    }

    // Check if user already has an organization
    try {
        const response = await authenticatedFetch('/api/organizations/check-onboarding');
        const data = await response.json();

        if (data.has_organization) {
            window.location.href = '/dashboard.html';
            return;
        }

        // Store user email and pre-fill org name from email domain
        if (data.user_email) {
            onboardingData.userEmail = data.user_email;

            // Pre-fill organization name from email domain
            const emailDomain = data.user_email.split('@')[1];
            if (emailDomain) {
                // Convert "acme.com" -> "Acme"
                const suggestedOrgName = emailDomain
                    .split('.')[0]
                    .charAt(0).toUpperCase() + emailDomain.split('.')[0].slice(1);

                document.getElementById('orgName').placeholder = suggestedOrgName;
                // Optionally pre-fill the value
                // document.getElementById('orgName').value = suggestedOrgName;
            }
        }
    } catch (error) {
        showError('step1Error', 'Failed to load onboarding status. Please refresh the page.');
    }

    // Set up form handlers
    setupFormHandlers();
}

/**
 * Set up form event handlers
 */
function setupFormHandlers() {
    // Organization form submission
    const orgForm = document.getElementById('orgForm');
    orgForm.addEventListener('submit', (e) => {
        e.preventDefault();
        validateStep1();
    });

    // Plan selection listeners
    document.querySelectorAll('input[name="plan"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            onboardingData.plan = e.target.value;
        });
    });

    // Auto-save form data on input
    document.getElementById('orgName').addEventListener('input', (e) => {
        onboardingData.orgName = e.target.value;
    });
}

/**
 * Validate step 1 and move to step 2
 */
function validateStep1() {
    const orgName = document.getElementById('orgName').value.trim();

    // Clear previous errors
    hideError('step1Error');

    // Validation
    if (!orgName || orgName.length < 2) {
        showError('step1Error', 'Please enter a valid organization name (at least 2 characters)');
        return;
    }

    // Update data
    onboardingData.orgName = orgName;

    // Move to next step
    nextStep();
}

/**
 * Create organization (Step 2 → Step 3)
 */
async function createOrganization() {
    // Get selected plan
    const selectedPlan = document.querySelector('input[name="plan"]:checked').value;
    onboardingData.plan = selectedPlan;

    // Disable button and show loading
    const button = event.target;
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="spinner"></span> Creating organization...';

    hideError('step2Error');

    try {
        // Call API to create organization
        const response = await authenticatedFetch('/api/organizations/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: onboardingData.orgName,
                billing_email: onboardingData.userEmail,  // Use email from OAuth
                subscription_plan: onboardingData.plan
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create organization');
        }

        const organization = await response.json();

        // Move to success step
        nextStep();

    } catch (error) {
        showError('step2Error', error.message || 'Failed to create organization. Please try again.');

        // Re-enable button
        button.disabled = false;
        button.innerHTML = originalText;
    }
}

/**
 * Go to next step
 */
function nextStep() {
    if (currentStep >= totalSteps) return;

    // Update step
    currentStep++;
    updateUI();
}

/**
 * Go to previous step
 */
function previousStep() {
    if (currentStep <= 1) return;

    // Update step
    currentStep--;
    updateUI();
}

/**
 * Update UI for current step
 */
function updateUI() {
    // Update step indicators
    document.querySelectorAll('.step').forEach((step, index) => {
        const stepNum = index + 1;

        step.classList.remove('active', 'completed');

        if (stepNum === currentStep) {
            step.classList.add('active');
        } else if (stepNum < currentStep) {
            step.classList.add('completed');
            step.querySelector('.step-circle').innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
        } else {
            step.querySelector('.step-circle').textContent = stepNum;
        }
    });

    // Update progress line
    const progressPercent = ((currentStep - 1) / (totalSteps - 1)) * 100;
    document.getElementById('progressLine').style.width = `${progressPercent}%`;

    // Update content visibility
    document.querySelectorAll('.step-content').forEach((content, index) => {
        content.classList.remove('active');
        if (index + 1 === currentStep) {
            content.classList.add('active');
        }
    });
}

/**
 * Redirect to dashboard after completion
 */
function goToDashboard() {
    window.location.href = '/dashboard.html';
}

/**
 * Email validation helper
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Show error message
 */
function showError(elementId, message) {
    const errorEl = document.getElementById(elementId);
    errorEl.textContent = message;
    errorEl.classList.add('show');
}

/**
 * Hide error message
 */
function hideError(elementId) {
    const errorEl = document.getElementById(elementId);
    errorEl.classList.remove('show');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initOnboarding);
