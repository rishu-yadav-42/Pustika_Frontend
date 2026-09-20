// API Bridge for Pustika Frontend & Backend Communication

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://127.0.0.1:5000/api'
  : 'https://pustika-backend.vercel.app/api'; // Replace with live Vercel Backend URL if needed

window.PustikaAPI = {
  baseUrl: API_BASE_URL,

  async request(endpoint, options = {}) {
    options.credentials = 'include';
    options.headers = options.headers || {};
    
    if (options.body && !(options.body instanceof FormData) && typeof options.body === 'object') {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'API Request failed');
      }
      return data;
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  // Auth Methods
  checkAuth() {
    return this.request('/me');
  },
  login(email, password) {
    return this.request('/login', { method: 'POST', body: { email, password } });
  },
  register(username, email, password) {
    return this.request('/register', { method: 'POST', body: { username, email, password } });
  },
  logout() {
    return this.request('/logout', { method: 'POST' });
  },

  // Books Methods
  getBooks(category = '', search = '') {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (search) params.append('q', search);
    return this.request(`/books?${params.toString()}`);
  },
  getBookDetail(bookId) {
    return this.request(`/books/${bookId}`);
  },
  createBook(formData) {
    return this.request('/books', { method: 'POST', body: formData });
  },
  deleteBook(bookId) {
    return this.request(`/books/${bookId}`, { method: 'DELETE' });
  },

  // Chapters & Audio Methods
  getChapter(chapterId) {
    return this.request(`/chapters/${chapterId}`);
  },
  getChapterAudio(chapterId) {
    return this.request(`/chapters/${chapterId}/audio`, { method: 'POST' });
  },

  // Categories
  getCategories() {
    return this.request('/categories');
  },

  // Favorites
  getFavorites() {
    return this.request('/favorites');
  },
  toggleFavorite(bookId) {
    return this.request(`/favorites/${bookId}`, { method: 'POST' });
  }
};
