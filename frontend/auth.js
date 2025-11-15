/**
 * Authentication utilities for DocuFlow
 * Handles Auth0 integration, token management, and user session
 */

let auth0Client = null;
let currentUser = null;

/**
 * Initialize Auth0 client
 * @returns {Promise<void>}
 */
async function initAuth() {
    try {
        // Fetch Auth0 configuration from backend
        const response = await fetch('/api/auth/config');
        if (!response.ok) {
            throw new Error('Failed to load Auth0 configuration');
        }

        const config = await response.json();

        // Create Auth0 client
        auth0Client = await auth0.createAuth0Client({
            domain: config.domain,
            clientId: config.client_id,
            authorizationParams: {
                redirect_uri: window.location.origin + '/login.html',
                audience: config.audience,
                scope: 'openid profile email'
            },
            cacheLocation: 'localstorage',
            useRefreshTokens: true
        });

        return auth0Client;
    } catch (error) {
        console.error('Auth initialization error:', error);
        throw error;
    }
}

/**
 * Check if user is authenticated
 * @returns {Promise<boolean>}
 */
async function isAuthenticated() {
    try {
        console.log('[Auth] Checking authentication...');

        // First check if we have a token in localStorage
        const storedToken = localStorage.getItem('auth_token');
        console.log('[Auth] Stored token exists:', !!storedToken);

        if (storedToken) {
            console.log('[Auth] User authenticated via localStorage');
            return true;
        }

        // If no stored token, check Auth0 client
        console.log('[Auth] No stored token, checking Auth0 client...');
        if (!auth0Client) {
            console.log('[Auth] Initializing Auth0 client...');
            await initAuth();
        }

        const authenticated = await auth0Client.isAuthenticated();
        console.log('[Auth] Auth0 client authentication result:', authenticated);
        return authenticated;
    } catch (error) {
        console.error('[Auth] Authentication check error:', error);
        // Final fallback: check localStorage
        const fallback = !!localStorage.getItem('auth_token');
        console.log('[Auth] Fallback authentication result:', fallback);
        return fallback;
    }
}

/**
 * Get authentication token
 * @returns {Promise<string|null>}
 */
async function getToken() {
    try {
        // First try localStorage (fastest and most reliable for stored sessions)
        const storedToken = localStorage.getItem('auth_token');
        if (storedToken) {
            console.log('[Auth] Using stored token from localStorage');
            return storedToken;
        }

        // If no stored token, try Auth0 client
        if (!auth0Client) {
            await initAuth();
        }

        // Get access token from Auth0
        const token = await auth0Client.getTokenSilently();
        console.log('[Auth] Got fresh token from Auth0');

        // Store for future use
        localStorage.setItem('auth_token', token);
        return token;
    } catch (error) {
        console.error('[Auth] Token retrieval error:', error);
        // Check localStorage one more time as fallback
        const fallbackToken = localStorage.getItem('auth_token');
        if (fallbackToken) {
            console.log('[Auth] Using fallback token from localStorage');
            return fallbackToken;
        }
        throw error;
    }
}

/**
 * Get current user information
 * @returns {Promise<object|null>}
 */
async function getCurrentUser() {
    if (currentUser) {
        return currentUser;
    }

    try {
        // First try localStorage (fastest)
        const storedUser = localStorage.getItem('user');
        if (storedUser) {
            currentUser = JSON.parse(storedUser);
            return currentUser;
        }

        // Then try Auth0 client
        if (!auth0Client) {
            await initAuth();
        }

        // Get user from Auth0
        const user = await auth0Client.getUser();

        if (user) {
            // Try to fetch full user info from backend (optional)
            try {
                const token = await getToken();
                if (token) {
                    const response = await fetch('/api/auth/user', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });

                    if (response.ok) {
                        currentUser = await response.json();
                        return currentUser;
                    }
                }
            } catch (backendError) {
                console.warn('Could not fetch user from backend, using Auth0 user:', backendError);
                // Continue with Auth0 user
            }
        }

        currentUser = user;
        return user;
    } catch (error) {
        console.error('Get user error:', error);
        return null;
    }
}

/**
 * Logout current user
 * @returns {Promise<void>}
 */
async function logout() {
    try {
        // Call backend logout endpoint
        const token = await getToken();
        if (token) {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
        }

        // Clear local storage
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        currentUser = null;

        // Logout from Auth0
        if (auth0Client) {
            await auth0Client.logout({
                logoutParams: {
                    returnTo: window.location.origin + '/login.html'
                }
            });
        } else {
            // Fallback: redirect to login
            window.location.href = '/login.html';
        }
    } catch (error) {
        console.error('Logout error:', error);
        // Force redirect to login even if logout fails
        window.location.href = '/login.html';
    }
}

/**
 * Redirect to login page if not authenticated
 * Also checks if user needs onboarding and redirects accordingly
 * @returns {Promise<void>}
 */
async function requireAuth() {
    console.log('[Auth] requireAuth called from:', window.location.pathname);
    const authenticated = await isAuthenticated();
    console.log('[Auth] requireAuth result:', authenticated);

    if (!authenticated) {
        console.log('[Auth] Not authenticated, redirecting to login...');
        console.log('[Auth] Token exists:', !!localStorage.getItem('auth_token'));
        console.log('[Auth] User exists:', !!localStorage.getItem('user'));
        window.location.href = '/login.html';
        return false;
    }

    console.log('[Auth] Authentication successful!');

    // Check if user needs onboarding (only for main app pages, not onboarding page itself)
    const currentPath = window.location.pathname;
    const isOnboardingPage = currentPath.includes('onboarding.html');

    if (!isOnboardingPage) {
        try {
            const response = await authenticatedFetch('/api/organizations/check-onboarding');
            if (response.ok) {
                const data = await response.json();

                if (data.needs_onboarding) {
                    console.log('[Auth] User needs onboarding, redirecting...');
                    window.location.href = '/onboarding.html';
                    return false;
                }

                console.log('[Auth] User has organization:', data.organization_id);
            }
        } catch (error) {
            console.warn('[Auth] Could not check onboarding status:', error);
            // Continue anyway - backend will handle it
        }
    }

    return true;
}

/**
 * Make authenticated API request
 * @param {string} url - API endpoint URL
 * @param {object} options - Fetch options
 * @returns {Promise<Response>}
 */
async function authenticatedFetch(url, options = {}) {
    try {
        const token = await getToken();

        if (!token) {
            throw new Error('No authentication token available');
        }

        // Add Authorization header
        const headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };

        const response = await fetch(url, {
            ...options,
            headers
        });

        // Handle 401 Unauthorized - redirect to login
        if (response.status === 401) {
            console.warn('Authentication expired, redirecting to login');
            window.location.href = '/login.html';
            throw new Error('Authentication expired');
        }

        return response;
    } catch (error) {
        console.error('Authenticated fetch error:', error);
        throw error;
    }
}

/**
 * Display user info in header
 * @param {string} elementId - ID of element to display user info
 * @returns {Promise<void>}
 */
async function displayUserInfo(elementId = 'userInfo') {
    try {
        const user = await getCurrentUser();
        const element = document.getElementById(elementId);

        if (user && element) {
            const email = user.email || user.name || 'User';
            element.innerHTML = `
                <span style="margin-right: 1rem; color: #4b5563;">
                    👤 ${email}
                </span>
                <button id="logoutBtn" style="
                    padding: 0.5rem 1rem;
                    background: white;
                    border: 1px solid #e5e7eb;
                    border-radius: 0.375rem;
                    cursor: pointer;
                    font-size: 0.875rem;
                    font-weight: 500;
                    color: #374151;
                    transition: background-color 0.2s;
                " onmouseover="this.style.backgroundColor='#f3f4f6'"
                   onmouseout="this.style.backgroundColor='white'">
                    Logout
                </button>
            `;

            // Add logout event listener
            document.getElementById('logoutBtn').addEventListener('click', logout);
        }
    } catch (error) {
        console.error('Display user info error:', error);
    }
}

// Export functions for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initAuth,
        isAuthenticated,
        getToken,
        getCurrentUser,
        logout,
        requireAuth,
        authenticatedFetch,
        displayUserInfo
    };
}
