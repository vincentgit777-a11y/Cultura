/* ==========================================================================
   TECHNOVANA — registration.js
   Usability enhancements for the registration form.

   IMPORTANT: the server validates every field again. This script only
   improves the experience — it never decides that a registration succeeded.
   ========================================================================== */

(function () {
  'use strict';

  var form = document.querySelector('.form[method="post"]');
  if (!form) { return; }

  var teamFields = form.querySelector('[data-team-fields]');
  var radios = Array.prototype.slice.call(form.querySelectorAll('input[name="entry_type"]'));
  var submitButton = form.querySelector('button[type="submit"]');

  /* ------------------------------------------------------------------
     Show the team fields only when a team entry is selected
     ------------------------------------------------------------------ */
  function applyEntryType() {
    var selected = radios.filter(function (radio) { return radio.checked; })[0];
    var isTeam = selected && selected.value === 'team';

    if (teamFields) {
      teamFields.hidden = !isTeam;
      teamFields.querySelectorAll('input').forEach(function (input) {
        input.disabled = !isTeam;
      });
    }
  }

  radios.forEach(function (radio) {
    radio.addEventListener('change', applyEntryType);
  });

  applyEntryType();

  /* ------------------------------------------------------------------
     Inline validation messages
     ------------------------------------------------------------------ */
  function fieldOf(input) {
    return input.closest('.field');
  }

  function clearError(input) {
    var field = fieldOf(input);
    if (!field) { return; }
    var message = field.querySelector('.field__error');
    if (message) { message.remove(); }
    input.removeAttribute('aria-invalid');
  }

  function showError(input, message) {
    clearError(input);
    var field = fieldOf(input);
    if (!field) { return; }

    var paragraph = document.createElement('p');
    paragraph.className = 'field__error';
    paragraph.textContent = message;
    field.appendChild(paragraph);

    input.setAttribute('aria-invalid', 'true');
  }

  var EMAIL = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

  function validate() {
    var valid = true;
    var firstInvalid = null;

    var name = form.querySelector('#full_name');
    if (name) {
      var nameValue = name.value.trim();
      if (!nameValue) {
        showError(name, 'Enter the participant’s full name.');
        valid = false;
        firstInvalid = firstInvalid || name;
      } else if (nameValue.length < 3) {
        showError(name, 'The full name must be at least 3 characters long.');
        valid = false;
        firstInvalid = firstInvalid || name;
      }
    }

    var email = form.querySelector('#email');
    if (email) {
      var emailValue = email.value.trim();
      if (!emailValue) {
        showError(email, 'Enter an email address so the organisers can reach you.');
        valid = false;
        firstInvalid = firstInvalid || email;
      } else if (!EMAIL.test(emailValue)) {
        showError(email, 'Enter a valid email address, for example name@example.edu.');
        valid = false;
        firstInvalid = firstInvalid || email;
      }
    }

    var department = form.querySelector('#department');
    if (department && !department.value) {
      showError(department, 'Select your department.');
      valid = false;
      firstInvalid = firstInvalid || department;
    }

    var year = form.querySelector('#academic_year');
    if (year && !year.value) {
      showError(year, 'Select your year of study.');
      valid = false;
      firstInvalid = firstInvalid || year;
    }

    // Team rules mirror the server-side rules.
    var selected = radios.filter(function (radio) { return radio.checked; })[0];
    if (selected && selected.value === 'team' && teamFields && !teamFields.hidden) {
      var memberInputs = Array.prototype.slice.call(
        teamFields.querySelectorAll('input[name="team_members"]')
      ).filter(function (input) { return !input.disabled; });

      var filled = memberInputs.filter(function (input) {
        return input.value.trim().length > 0;
      });

      var min = parseInt(
        memberInputs[0] ? memberInputs[0].getAttribute('data-min') : '0', 10
      );

      if (min && filled.length < min) {
        showError(memberInputs[0], 'List at least ' + min + ' team member name(s).');
        valid = false;
        firstInvalid = firstInvalid || memberInputs[0];
      }

      var teamName = form.querySelector('#team_name');
      if (teamName && !teamName.value.trim()) {
        showError(teamName, 'Enter a name for your team.');
        valid = false;
        firstInvalid = firstInvalid || teamName;
      }
    }

    if (firstInvalid && firstInvalid.focus) { firstInvalid.focus(); }
    return valid;
  }

  form.addEventListener('submit', function (event) {
    if (!validate()) {
      event.preventDefault();
      return;
    }

    // A short "sending" state stops double submissions. The server still
    // decides whether the registration is accepted.
    if (submitButton) {
      submitButton.setAttribute('aria-disabled', 'true');
      submitButton.dataset.originalLabel = submitButton.textContent;
      submitButton.textContent = 'Submitting…';
      window.setTimeout(function () {
        submitButton.removeAttribute('aria-disabled');
        submitButton.textContent = submitButton.dataset.originalLabel || 'Confirm registration';
      }, 6000);
    }
  });

  form.addEventListener('input', function (event) {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'SELECT') {
      clearError(event.target);
    }
  });
})();
