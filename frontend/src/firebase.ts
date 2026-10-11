// OM Search — Firebase Web App Initialization
import { initializeApp } from "firebase/app";
import { getAnalytics, isSupported } from "firebase/analytics";

const firebaseConfig = {
  apiKey: "AIzaSyBhpQW-3qD_MZNOaGN2hXscOakV5zCggAA",
  authDomain: "one-for-all-5e842.firebaseapp.com",
  projectId: "one-for-all-5e842",
  storageBucket: "one-for-all-5e842.firebasestorage.app",
  messagingSenderId: "993610150510",
  appId: "1:993610150510:web:957dc97f1427a91320ec7f",
  measurementId: "G-QRVDB09X0Y",
};

// Initialize Firebase
export const app = initializeApp(firebaseConfig);

// Initialize Analytics conditionally (only when supported in browser environment)
export let analytics: any = null;
if (typeof window !== "undefined") {
  isSupported().then((supported) => {
    if (supported) {
      analytics = getAnalytics(app);
    }
  });
}
