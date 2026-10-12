import { auth } from './firebase-config.js';
import { 
    createUserWithEmailAndPassword, 
    signInWithEmailAndPassword, 
    signOut, 
    sendPasswordResetEmail, 
    onAuthStateChanged,
    updateProfile,
    GoogleAuthProvider,
    OAuthProvider,
    signInWithPopup
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

function getFriendlyErrorMessage(error) {
    switch (error.code) {
        case 'auth/invalid-email': return 'Invalid email address format.';
        case 'auth/user-disabled': return 'This account has been disabled.';
        case 'auth/user-not-found': return 'No account found with this email.';
        case 'auth/wrong-password': return 'Incorrect password. Please try again.';
        case 'auth/invalid-credential': return 'Incorrect email or password.';
        case 'auth/email-already-in-use': return 'An account already exists with this email address.';
        case 'auth/weak-password': return 'Password is too weak. Please use at least 6 characters.';
        case 'auth/too-many-requests': return 'Too many failed login attempts. Please try again later.';
        case 'auth/network-request-failed': return 'Network error. Please check your internet connection.';
        case 'auth/popup-closed-by-user': return 'Sign-in popup was closed before completing.';
        default: return error.message ? error.message.replace('Firebase: ', '') : 'An error occurred during authentication.';
    }
}

export async function registerUser(email, password, displayName) {
    try {
        const userCredential = await createUserWithEmailAndPassword(auth, email, password);
        if (displayName) {
            await updateProfile(userCredential.user, { displayName: displayName });
        }
        
        // Call backend to create profile
        const token = await userCredential.user.getIdToken();
        await fetch('/api/auth/create-profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ display_name: displayName || email.split('@')[0], email })
        }).catch(err => console.error("Profile creation warning:", err));
        
        return userCredential.user;
    } catch (error) {
        throw new Error(getFriendlyErrorMessage(error));
    }
}

export async function loginUser(email, password) {
    try {
        const userCredential = await signInWithEmailAndPassword(auth, email, password);
        return userCredential.user;
    } catch (error) {
        throw new Error(getFriendlyErrorMessage(error));
    }
}

export async function loginWithGoogle() {
    try {
        const provider = new GoogleAuthProvider();
        const userCredential = await signInWithPopup(auth, provider);
        const user = userCredential.user;
        const token = await user.getIdToken();
        await fetch('/api/auth/create-profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ display_name: user.displayName || user.email.split('@')[0], email: user.email })
        }).catch(err => console.error("Profile creation warning:", err));
        return user;
    } catch (error) {
        throw new Error(getFriendlyErrorMessage(error));
    }
}

export async function loginWithMicrosoft() {
    try {
        const provider = new OAuthProvider('microsoft.com');
        const userCredential = await signInWithPopup(auth, provider);
        const user = userCredential.user;
        const token = await user.getIdToken();
        await fetch('/api/auth/create-profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ display_name: user.displayName || user.email.split('@')[0], email: user.email })
        }).catch(err => console.error("Profile creation warning:", err));
        return user;
    } catch (error) {
        throw new Error(getFriendlyErrorMessage(error));
    }
}

export function logoutUser() {
    return signOut(auth).then(() => {
        window.location.href = '/login';
    });
}

export async function resetPassword(email) {
    try {
        return await sendPasswordResetEmail(auth, email);
    } catch (error) {
        throw new Error(getFriendlyErrorMessage(error));
    }
}

export function getCurrentUser() {
    return auth.currentUser;
}

let _cachedToken = null;
let _tokenExpiresAt = 0;
let _refreshPromise = null;

export function getIdToken(forceRefresh = false) {
    const now = Date.now();
    if (!forceRefresh && _cachedToken && now < _tokenExpiresAt) {
        return Promise.resolve(_cachedToken);
    }
    if (_refreshPromise) {
        return _refreshPromise;
    }

    _refreshPromise = new Promise((resolve, reject) => {
        const user = auth.currentUser;
        if (user) {
            user.getIdToken(forceRefresh).then(token => {
                _cachedToken = token;
                _tokenExpiresAt = Date.now() + 5 * 60 * 1000;
                resolve(token);
            }).catch(err => {
                _cachedToken = null;
                _tokenExpiresAt = 0;
                reject(err);
            }).finally(() => {
                _refreshPromise = null;
            });
        } else {
            const unsubscribe = onAuthStateChanged(auth, (u) => {
                unsubscribe();
                if (u) {
                    u.getIdToken(forceRefresh).then(token => {
                        _cachedToken = token;
                        _tokenExpiresAt = Date.now() + 5 * 60 * 1000;
                        resolve(token);
                    }).catch(err => {
                        _cachedToken = null;
                        _tokenExpiresAt = 0;
                        reject(err);
                    }).finally(() => {
                        _refreshPromise = null;
                    });
                } else {
                    _cachedToken = null;
                    _tokenExpiresAt = 0;
                    _refreshPromise = null;
                    resolve(null);
                }
            });
        }
    });

    return _refreshPromise;
}


export function onAuthChange(callback) {
    return onAuthStateChanged(auth, callback);
}
