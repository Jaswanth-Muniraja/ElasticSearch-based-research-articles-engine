// firebase.js
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "qwertyuiop-asdfghjklzxcvbnm",
  authDomain: "qwertyuiop.firebaseapp.com",
  projectId: "qwertyuiop",
  storageBucket: "qwertyuiop.firebasestorage.app",
  messagingSenderId: "1234567890",
  appId: "qwertyuiop1234567890asdfghjklzxcvbnm",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);
