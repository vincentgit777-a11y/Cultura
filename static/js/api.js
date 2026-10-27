/* ==========================================================================
   CULTURA — api.js
   Centralized API client for communicating with the backend.
   ========================================================================== */

(function () {
  'use strict';

  /**
   * Get the base API URL. In this server-rendered app, API endpoints
   * are on the same origin.
   */
  var API_BASE = '';

  /**
   * Get the CSRF token from the meta tag or form.
   */
  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');

    var input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;

    return '';
  }

  /**
   * Default headers for API requests.
   */
  function getHeaders(contentType) {
    var headers = {
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    };
    if (contentType) {
      headers['Content-Type'] = contentType;
    }
    var csrf = getCsrfToken();
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }
    return headers;
  }

  /**
   * Handle response - parse JSON and check for errors.
   */
  function handleResponse(response) {
    var contentType = response.headers.get('Content-Type') || '';
    if (contentType.indexOf('application/json') !== -1) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var error = data.error || { message: 'Request failed' };
          throw new ApiError(response.status, error.code, error.message, error.details);
        }
        return data;
      });
    } else {
      return response.text().then(function (text) {
        if (!response.ok) {
          throw new ApiError(response.status, 'HTTP_ERROR', 'Request failed: ' + response.statusText);
        }
        return text;
      });
    }
  }

  /**
   * Custom error class for API errors.
   */
  function ApiError(status, code, message, details) {
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.message = message;
    this.details = details;
    this.stack = (new Error()).stack;
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  /**
   * Make an API request.
   */
  function request(path, options) {
    options = options || {};
    var method = (options.method || 'GET').toUpperCase();
    var headers = getHeaders(options.headers ? undefined : 'application/json');
    var body = options.body;

    // Merge custom headers
    if (options.headers) {
      Object.keys(options.headers).forEach(function (key) {
        headers[key] = options.headers[key];
      });
    }

    // Stringify body for non-GET requests
    if (body && method !== 'GET' && method !== 'HEAD') {
      if (typeof body === 'object' && !(body instanceof FormData)) {
        body = JSON.stringify(body);
      }
    }

    var fetchOptions = {
      method: method,
      headers: headers,
      credentials: 'same-origin', // Include cookies for session auth
    };

    if (body && method !== 'GET' && method !== 'HEAD') {
      fetchOptions.body = body;
    }

    return fetch(API_BASE + path, fetchOptions).then(handleResponse);
  }

  /**
   * Convenience methods.
   */
  var api = {
    get: function (path) {
      return request(path, { method: 'GET' });
    },
    post: function (path, data) {
      return request(path, { method: 'POST', body: data });
    },
    put: function (path, data) {
      return request(path, { method: 'PUT', body: data });
    },
    patch: function (path, data) {
      return request(path, { method: 'PATCH', body: data });
    },
    delete: function (path) {
      return request(path, { method: 'DELETE' });
    },

    // Authentication
    auth: {
      login: function (email, password) {
        return api.post('/api/auth/login', { email: email, password: password });
      },
      register: function (data) {
        return api.post('/api/auth/register', data);
      },
      logout: function () {
        return api.post('/api/auth/logout', {});
      },
      me: function () {
        return api.get('/api/auth/me');
      },
    },

    // Student dashboard
    student: {
      dashboard: function () {
        return api.get('/api/student/dashboard');
      },
      registrations: function () {
        return api.get('/api/student/registrations');
      },
      registerForEvent: function (eventSlug, data) {
        return api.post('/api/events/' + encodeURIComponent(eventSlug) + '/register', data);
      },
      teams: function () {
        return api.get('/api/student/teams');
      },
      createTeam: function (data) {
        return api.post('/api/student/teams', data);
      },
      profile: function () {
        return api.get('/api/student/profile');
      },
      updateProfile: function (data) {
        return api.put('/api/student/profile', data);
      },
    },

    // Admin API
    admin: {
      dashboard: function () {
        return api.get('/api/admin/dashboard');
      },
      events: {
        list: function (params) {
          var query = new URLSearchParams(params).toString();
          return api.get('/api/admin/events' + (query ? '?' + query : ''));
        },
        get: function (slug) {
          return api.get('/api/admin/events/' + encodeURIComponent(slug));
        },
        create: function (data) {
          return api.post('/api/admin/events', data);
        },
        update: function (slug, data) {
          return api.put('/api/admin/events/' + encodeURIComponent(slug), data);
        },
        delete: function (slug) {
          return api.delete('/api/admin/events/' + encodeURIComponent(slug));
        },
        publish: function (slug) {
          return api.post('/api/admin/events/' + encodeURIComponent(slug) + '/publish', {});
        },
        unpublish: function (slug) {
          return api.post('/api/admin/events/' + encodeURIComponent(slug) + '/unpublish', {});
        },
      },
      competitions: {
        list: function (params) {
          var query = new URLSearchParams(params).toString();
          return api.get('/api/admin/competitions' + (query ? '?' + query : ''));
        },
        get: function (slug) {
          return api.get('/api/admin/competitions/' + encodeURIComponent(slug));
        },
        create: function (data) {
          return api.post('/api/admin/competitions', data);
        },
        update: function (slug, data) {
          return api.put('/api/admin/competitions/' + encodeURIComponent(slug), data);
        },
        delete: function (slug) {
          return api.delete('/api/admin/competitions/' + encodeURIComponent(slug));
        },
      },
      registrations: {
        list: function (params) {
          var query = new URLSearchParams(params).toString();
          return api.get('/api/admin/registrations' + (query ? '?' + query : ''));
        },
        get: function (id) {
          return api.get('/api/admin/registrations/' + encodeURIComponent(id));
        },
        updateStatus: function (id, status) {
          return api.patch('/api/admin/registrations/' + encodeURIComponent(id), { status: status });
        },
      },
      teams: {
        list: function (params) {
          var query = new URLSearchParams(params).toString();
          return api.get('/api/admin/teams' + (query ? '?' + query : ''));
        },
        get: function (id) {
          return api.get('/api/admin/teams/' + encodeURIComponent(id));
        },
      },
      schedule: {
        list: function (params) {
          var query = new URLSearchParams(params).toString();
          return api.get('/api/admin/schedule' + (query ? '?' + query : ''));
        },
        get: function (id) {
          return api.get('/api/admin/schedule/' + encodeURIComponent(id));
        },
        create: function (data) {
          return api.post('/api/admin/schedule', data);
        },
        update: function (id, data) {
          return api.put('/api/admin/schedule/' + encodeURIComponent(id), data);
        },
        delete: function (id) {
          return api.delete('/api/admin/schedule/' + encodeURIComponent(id));
        },
      },
      posters: {
        list: function () {
          return api.get('/api/admin/posters');
        },
        get: function (id) {
          return api.get('/api/admin/posters/' + encodeURIComponent(id));
        },
        create: function (data) {
          return api.post('/api/admin/posters', data);
        },
        update: function (id, data) {
          return api.put('/api/admin/posters/' + encodeURIComponent(id), data);
        },
        delete: function (id) {
          return api.delete('/api/admin/posters/' + encodeURIComponent(id));
        },
        download: function (id) {
          return api.get('/api/admin/posters/' + encodeURIComponent(id) + '/download');
        },
      },
      settings: {
        get: function () {
          return api.get('/api/admin/settings');
        },
        update: function (data) {
          return api.put('/api/admin/settings', data);
        },
      },
    },
  };

  // Expose globally
  window.CulturaApi = api;
  window.ApiError = ApiError;

})();