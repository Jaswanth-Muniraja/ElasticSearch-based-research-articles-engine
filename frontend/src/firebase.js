// firebase.js
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyAtWfV-vuZ7qXt6IdPzpP068rtwPHGqaJ0",
  authDomain: "researchhubsdp.firebaseapp.com",
  projectId: "researchhubsdp",
  storageBucket: "researchhubsdp.firebasestorage.app",
  messagingSenderId: "33812798653",
  appId: "1:33812798653:web:57dd75d06e9beef5da6bd4",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);