import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
});

const readData = async (request) => {
  const response = await request;
  return response.data;
};

export const fetchStats = async () => readData(api.get('/dashboard/stats'));

export const fetchReports = async (limit = 10) =>
  readData(api.get('/dashboard/reports', { params: { limit } }));

export const fetchHeatmap = async () => readData(api.get('/dashboard/heatmap'));

export const fetchTrends = async (days = 7) =>
  readData(api.get('/dashboard/trends', { params: { days } }));

export const fetchNetwork = async () => readData(api.get('/dashboard/network'));

export const fetchPhoneDetails = async (number) =>
  readData(api.get(`/lookup/phone/${encodeURIComponent(number)}`));

export const createReport = async (payload) =>
  readData(api.post('/reports', payload));
