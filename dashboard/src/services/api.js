import axios from 'axios';

// Base API instance (placeholder for real backend)
const api = axios.create({
  baseURL: '/api',
});

// Mock Delay Helper
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Fallback Mock Data
const mockStats = {
  totalReports: 125430,
  suspiciousNumbers: 8740,
  detectedSyndicates: 142,
  verifiedCompanies: 3254,
};

const mockReports = [
  { id: 1, phone: "+91 98765 43210", message: "URGENT: Your HDFC bank account is blocked. Click here to KYC...", riskScore: "High Risk", location: "Delhi", timestamp: "2026-03-14 10:15 AM" },
  { id: 2, phone: "+91 87654 32109", message: "Congratulations! You have been selected for a remote part-time job earning 5000/day.", riskScore: "High Risk", location: "Maharashtra", timestamp: "2026-03-14 09:45 AM" },
  { id: 3, phone: "+91 76543 21098", message: "Amazon HR: Your interview is scheduled. Pay 500 Rs registration fee.", riskScore: "Suspicious", location: "Karnataka", timestamp: "2026-03-14 09:12 AM" },
  { id: 4, phone: "+91 65432 10987", message: "Your electricity connection will be cut tonight. Call immediately.", riskScore: "High Risk", location: "Uttar Pradesh", timestamp: "2026-03-14 08:30 AM" },
  { id: 5, phone: "+91 54321 09876", message: "Your OTP for Flipkart login is 459812. Do not share.", riskScore: "Safe", location: "Tamil Nadu", timestamp: "2026-03-14 08:05 AM" },
  { id: 6, phone: "+91 99999 88888", message: "Pending IT Refund of 45,000 INR. Click wxy.in/refund", riskScore: "High Risk", location: "Bihar", timestamp: "2026-03-13 11:20 PM" },
];

const mockHeatmap = [
  { state: "Maharashtra", count: 420 },
  { state: "Delhi", count: 380 },
  { state: "Uttar Pradesh", count: 350 },
  { state: "Karnataka", count: 290 },
  { state: "West Bengal", count: 210 },
  { state: "Tamil Nadu", count: 180 },
  { state: "Bihar", count: 150 },
  { state: "Rajasthan", count: 130 },
  { state: "Gujarat", count: 110 },
  { state: "Telangana", count: 90 },
];

const mockTrends = [
  { date: "03-08", count: 120 },
  { date: "03-09", count: 145 },
  { date: "03-10", count: 160 },
  { date: "03-11", count: 130 },
  { date: "03-12", count: 195 },
  { date: "03-13", count: 210 },
  { date: "03-14", count: 250 },
];

const mockNetwork = {
  nodes: [
    { id: "+91 98765 43210", group: 1, label: "Phone Number" },
    { id: "fraud@upi", group: 2, label: "UPI ID" },
    { id: "Ramesh Agent", group: 3, label: "Agent Name" },
    { id: "Fake Corp Ltd", group: 4, label: "Company Name" },
    { id: "+91 87654 32109", group: 1, label: "Phone Number" },
    { id: "scammer@okaxis", group: 2, label: "UPI ID" },
    { id: "Suresh Caller", group: 3, label: "Agent Name" }
  ],
  links: [
    { source: "+91 98765 43210", target: "fraud@upi", value: 1 },
    { source: "+91 98765 43210", target: "Ramesh Agent", value: 1 },
    { source: "Ramesh Agent", target: "Fake Corp Ltd", value: 2 },
    { source: "+91 87654 32109", target: "scammer@okaxis", value: 1 },
    { source: "scammer@okaxis", target: "Suresh Caller", value: 1 },
    { source: "Suresh Caller", target: "Fake Corp Ltd", value: 2 },
    { source: "+91 87654 32109", target: "fraud@upi", value: 1 } // Connection showing syndicate
  ]
};

// API Methods
export const fetchStats = async () => {
  try {
    // const response = await api.get('/stats');
    // return response.data;
    await delay(600);
    return mockStats;
  } catch (error) {
    console.error("Error fetching stats, falling back to mock data", error);
    await delay(300);
    return mockStats;
  }
};

export const fetchReports = async () => {
  try {
    // const response = await api.get('/reports');
    // return response.data;
    await delay(800);
    return mockReports;
  } catch (error) {
    return mockReports;
  }
};

export const fetchHeatmap = async () => {
  try {
    await delay(500);
    return mockHeatmap;
  } catch (error) {
    return mockHeatmap;
  }
};

export const fetchPhoneDetails = async (number) => {
  try {
    await delay(800);
    // Simulate lookup logic based on formatting to demonstrate fallback
    const isSafe = number.includes("543210");
    return {
      number,
      riskScore: isSafe ? "Safe" : "High Risk",
      reportCount: isSafe ? 0 : 24,
      companies: isSafe ? ["Verified Tech Solutions"] : ["Fake Corp Ltd", "Scam Info Systems"],
      upiIds: isSafe ? [] : ["fraud@upi", "scammer@okaxis"],
      lastSeen: isSafe ? "N/A" : "2 mins ago"
    };
  } catch (error) {
    throw new Error("Could not fetch phone details");
  }
};

export const fetchTrends = async () => {
  try {
    await delay(700);
    return mockTrends;
  } catch (error) {
    return mockTrends;
  }
};

export const fetchNetwork = async () => {
  try {
    await delay(1000);
    return mockNetwork;
  } catch (error) {
    return mockNetwork;
  }
};
