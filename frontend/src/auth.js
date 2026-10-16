// Logging in, through Google Cloud Identity Platform.
//
// Google's Firebase library does the work: it shows Google's sign-in, keeps the person logged in
// between visits, and gives us a fresh login token (a signed JWT) whenever we ask. We send that
// token with every API call, and each service checks it. We never see anyone's password.
import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from "firebase/auth";

let auth = null;

// Set up login. The project details come from meal-logging rather than being built in, so the
// same website build works anywhere. `onUserChange` is called with the user (or null) whenever
// someone logs in or out.
export async function startAuth(onUserChange) {
  const response = await fetch("/api/meals/auth/config");
  if (!response.ok) throw new Error("Can't reach MacroScope to set up logging in. Is it running?");
  const config = await response.json();
  const app = initializeApp({ apiKey: config.api_key, authDomain: config.auth_domain, projectId: config.project_id });
  auth = getAuth(app);
  onAuthStateChanged(auth, onUserChange);
}

// The current login token, or null if nobody is logged in. Firebase renews it when it's about to
// expire (they last an hour), so this is always safe to call.
export async function getToken() {
  return auth?.currentUser ? auth.currentUser.getIdToken() : null;
}

export const logIn = (email, password) => signInWithEmailAndPassword(auth, email, password);
export const signUp = (email, password) => createUserWithEmailAndPassword(auth, email, password);
export const logInWithGoogle = () => signInWithPopup(auth, new GoogleAuthProvider());
export const logOut = () => signOut(auth);

// Turn Firebase's error codes into something a person can act on
const MESSAGES = {
  "auth/invalid-credential": "Wrong email or password.",
  "auth/invalid-email": "That doesn't look like an email address.",
  "auth/email-already-in-use": "There's already an account with that email. Try logging in.",
  "auth/weak-password": "Please use a password of at least 6 characters.",
  "auth/too-many-requests": "Too many tries. Please wait a minute and try again.",
  "auth/popup-closed-by-user": "The Google sign-in window was closed.",
  "auth/operation-not-allowed": "That way of logging in isn't turned on for this project yet.",
};

export function loginError(error) {
  return MESSAGES[error.code] || error.message;
}
