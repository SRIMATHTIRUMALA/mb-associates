/**
 * MB Associates Solar Website — Customer Enquiry Form Submission Handler
 * Replaces demo Stitch submission with real server-backed POST /api/enquiries.
 * Supports idempotency, server validation, error feedback, and seamless redirect.
 * Handles both main enquiry form (#solarRequestForm) and contact page forms (#quotePanel, #auditPanel).
 */

document.addEventListener('DOMContentLoaded', function () {
  // 1. Main Enquiry Form (enquiry.html)
  const solarForm = document.getElementById('solarRequestForm');
  if (solarForm) {
    initSolarEnquiryForm(solarForm);
  }

  // 2. Contact Page Forms (contact.html)
  const quoteForm = document.getElementById('quotePanel');
  if (quoteForm) {
    quoteForm.removeAttribute('onsubmit');
    quoteForm.addEventListener('submit', handleQuoteFormSubmit);
  }

  const auditForm = document.getElementById('auditPanel');
  if (auditForm) {
    auditForm.removeAttribute('onsubmit');
    auditForm.addEventListener('submit', handleAuditFormSubmit);
  }
});

/**
 * Initializes the main solarRequestForm on enquiry.html
 */
function initSolarEnquiryForm(form) {
  const urlParams = new URLSearchParams(window.location.search);
  const hash = window.location.hash;
  const isSiteVisit = urlParams.get('type') === 'site_visit' || 
                      urlParams.get('request_type') === 'site_visit' || 
                      hash === '#site-visit' ||
                      urlParams.get('action') === 'site_visit';

  if (isSiteVisit) {
    const checklist = document.getElementById('assistanceChecklist');
    if (checklist) {
      const feasibilityCheckbox = checklist.querySelector('input[value="Solar Feasibility Assessment"]');
      if (feasibilityCheckbox) feasibilityCheckbox.checked = true;
    }
    form.dataset.requestType = 'site_visit';
  } else {
    form.dataset.requestType = 'general';
  }

  const billParam = urlParams.get('bill');
  if (billParam && document.getElementById('monthlyBill')) {
    document.getElementById('monthlyBill').value = billParam;
  }
  const roofParam = urlParams.get('roof_area');
  if (roofParam && document.getElementById('roofArea')) {
    document.getElementById('roofArea').value = roofParam;
  }

  form.removeAttribute('onsubmit');
  form.addEventListener('submit', handleSolarFormSubmit);

  const submitBtn = document.getElementById('submitButton');
  if (submitBtn && submitBtn.tagName === 'A') {
    submitBtn.addEventListener('click', function (e) {
      e.preventDefault();
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      }
    });
  }
}

/**
 * Submit handler for main enquiry form (#solarRequestForm)
 */
async function handleSolarFormSubmit(event) {
  event.preventDefault();

  const form = event.target || document.getElementById('solarRequestForm');
  const submitBtn = document.getElementById('submitButton');
  const alertContainer = getOrCreateAlertContainer(form);

  alertContainer.innerHTML = '';
  alertContainer.classList.add('hidden');

  const nameInput = document.getElementById('fullName');
  const contactMethodSelect = document.getElementById('contactMethod');
  const contactDetailInput = document.getElementById('contactDetail');
  const pinCodeInput = document.getElementById('pinCode');
  const propertyTypeSelect = document.getElementById('propertyType');
  const roofAreaInput = document.getElementById('roofArea');
  const monthlyBillInput = document.getElementById('monthlyBill');
  const userNotesInput = document.getElementById('userNotes');
  const consentCheckbox = document.getElementById('consentCheckbox');

  const assistanceCheckboxes = form.querySelectorAll('input[name="helpScope"]:checked');
  const assistance = Array.from(assistanceCheckboxes).map(cb => cb.value);

  if (!consentCheckbox || !consentCheckbox.checked) {
    showFormError(alertContainer, 'Please confirm your consent to be contacted regarding your solar enquiry.');
    consentCheckbox?.focus();
    return;
  }

  const payload = {
    name: (nameInput?.value || '').trim(),
    contact_method: contactMethodSelect?.value || 'phone',
    contact_detail: (contactDetailInput?.value || '').trim(),
    pin_code: (pinCodeInput?.value || '').trim(),
    property_type: propertyTypeSelect?.value || '',
    request_type: form.dataset.requestType || 'general',
    assistance: assistance.length > 0 ? assistance : ['Solar Feasibility Assessment'],
    roof_area: roofAreaInput?.value?.trim() || null,
    monthly_bill: monthlyBillInput?.value ? parseFloat(monthlyBillInput.value) : null,
    notes: userNotesInput?.value?.trim() || null,
    consent: true
  };

  await executeSubmission(payload, form, submitBtn, alertContainer);
}

/**
 * Submit handler for Quote Panel (#quotePanel on contact.html)
 */
async function handleQuoteFormSubmit(event) {
  event.preventDefault();

  const form = event.target || document.getElementById('quotePanel');
  const submitBtn = form.querySelector('button[type="submit"]');
  const alertContainer = getOrCreateAlertContainer(form);

  alertContainer.innerHTML = '';
  alertContainer.classList.add('hidden');

  const nameInput = form.querySelector('#fullName') || form.querySelector('input[name="fullName"]');
  const phoneInput = form.querySelector('#phoneContact') || form.querySelector('input[name="phoneContact"]');
  const emailInput = form.querySelector('#emailContact') || form.querySelector('input[name="emailContact"]');
  const pinInput = form.querySelector('#quotePinCode') || form.querySelector('#pinDistrict') || form.querySelector('#pinCode');
  const billInput = form.querySelector('#monthlyBill') || form.querySelector('input[name="monthlyBill"]');
  const roofInput = form.querySelector('#roofAreaLoad');
  const categoryRadio = form.querySelector('input[name="projectCategory"]:checked');
  const consentCheck = form.querySelector('#quoteConsent') || form.querySelector('input[name="consent"]');

  if (consentCheck && !consentCheck.checked) {
    showFormError(alertContainer, 'Please confirm your consent to be contacted regarding your solar requirements.');
    consentCheck.focus();
    return;
  }

  // Extract clean 6-digit PIN code
  const rawPin = pinInput?.value || '';
  const pinMatch = rawPin.match(/\b\d{6}\b/) || rawPin.replace(/\D/g, '').match(/^\d{6}$/);
  const cleanPin = pinMatch ? (typeof pinMatch === 'string' ? pinMatch : pinMatch[0]) : rawPin.replace(/\D/g, '').slice(0, 6);

  const phoneVal = (phoneInput?.value || '').replace(/\D/g, '');
  const emailVal = (emailInput?.value || '').trim();
  const contactDetail = phoneVal.length >= 10 ? phoneVal.slice(-10) : emailVal;
  const contactMethod = phoneVal.length >= 10 ? 'phone' : 'email';

  const categoryMap = {
    'Residential': 'Residential Villa',
    'Society': 'Housing Society',
    'Commercial': 'Commercial',
    'Industrial': 'Industrial'
  };
  const propType = categoryMap[categoryRadio?.value] || categoryRadio?.value || 'Residential Villa';

  const payload = {
    name: (nameInput?.value || '').trim(),
    contact_method: contactMethod,
    contact_detail: contactDetail,
    pin_code: cleanPin,
    property_type: propType,
    request_type: 'general',
    assistance: ['Solar Feasibility Assessment', 'Subsidy Guidance', 'Loan Application Guidance'],
    roof_area: roofInput?.value?.trim() || null,
    monthly_bill: billInput?.value ? parseFloat(billInput.value) : null,
    notes: `Customer contact: Phone: ${phoneInput?.value || 'N/A'}, Email: ${emailVal || 'N/A'}`,
    consent: true
  };

  await executeSubmission(payload, form, submitBtn, alertContainer);
}

/**
 * Submit handler for Audit Panel (#auditPanel on contact.html)
 */
async function handleAuditFormSubmit(event) {
  event.preventDefault();

  const form = event.target || document.getElementById('auditPanel');
  const submitBtn = form.querySelector('button[type="submit"]');
  const alertContainer = getOrCreateAlertContainer(form);

  alertContainer.innerHTML = '';
  alertContainer.classList.add('hidden');

  const nameInput = form.querySelector('#auditName');
  const mobileInput = form.querySelector('#auditMobile');
  const dateInput = form.querySelector('#preferredDate');
  const addressInput = form.querySelector('#siteAddress');
  const pinInput = form.querySelector('#auditPinCode') || form.querySelector('#pinCode');
  const obstructionsSelect = form.querySelector('#obstructions');
  const inverterSelect = form.querySelector('#inverterPref');
  const notesInput = form.querySelector('#auditNotes');
  const propSelect = form.querySelector('#auditPropertyType');
  const consentCheck = form.querySelector('#auditConsent') || form.querySelector('input[name="consent"]');

  if (consentCheck && !consentCheck.checked) {
    showFormError(alertContainer, 'Please confirm your consent to be contacted regarding your site inspection request.');
    consentCheck.focus();
    return;
  }

  // Extract clean 6-digit PIN
  const rawPin = pinInput?.value || addressInput?.value || '';
  const pinMatch = rawPin.match(/\b\d{6}\b/) || rawPin.replace(/\D/g, '').match(/^\d{6}$/);
  const cleanPin = pinMatch ? (typeof pinMatch === 'string' ? pinMatch : pinMatch[0]) : rawPin.replace(/\D/g, '').slice(0, 6);

  const phoneVal = (mobileInput?.value || '').replace(/\D/g, '');
  const contactDetail = phoneVal.length >= 10 ? phoneVal.slice(-10) : (mobileInput?.value || '').trim();

  const siteNotes = [
    `Preferred Date: ${dateInput?.value || 'Flexible'}`,
    `Site Address: ${addressInput?.value || 'N/A'}`,
    `Obstructions: ${obstructionsSelect?.value || 'None'}`,
    `Inverter Preference: ${inverterSelect?.value || 'Engineer Recommendation'}`,
    notesInput?.value ? `Additional Remarks: ${notesInput.value.trim()}` : ''
  ].filter(Boolean).join('\n');

  const payload = {
    name: (nameInput?.value || '').trim(),
    contact_method: 'phone',
    contact_detail: contactDetail,
    pin_code: cleanPin,
    property_type: propSelect?.value || 'Residential Villa',
    request_type: 'site_visit',
    assistance: ['Solar Feasibility Assessment', 'Matching Nearby Verified Vendors', 'Installation Coordination'],
    roof_area: null,
    monthly_bill: null,
    notes: siteNotes,
    consent: true
  };

  await executeSubmission(payload, form, submitBtn, alertContainer);
}

/**
 * Common submission logic to /api/enquiries with error handling and session storage
 */
async function executeSubmission(payload, form, submitBtn, alertContainer) {
  setSubmitLoading(submitBtn, true);

  try {
    const response = await fetch('/api/enquiries', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json().catch(() => ({}));

    if (response.ok) {
      const enquirySession = {
        reference: data.reference,
        status: data.status,
        created_at: data.created_at,
        name: payload.name,
        contact_method: payload.contact_method,
        contact_detail: payload.contact_detail,
        property_type: payload.property_type,
        pin_code: payload.pin_code,
        assistance: payload.assistance,
        is_duplicate: Boolean(data.is_duplicate)
      };
      sessionStorage.setItem('mb_enquiry', JSON.stringify(enquirySession));

      window.location.href = '/enquiry-confirmation';
      return;
    }

    if (response.status === 409) {
      showFormConflict(
        alertContainer,
        data.detail || 'An enquiry with these contact details already exists with different request parameters. Your previous inputs have been preserved. Please review or contact our desk.'
      );
      setSubmitLoading(submitBtn, false);
      return;
    }

    if (response.status === 422) {
      let errorMsg = 'Please correct the highlighted fields:';
      if (Array.isArray(data.detail)) {
        const fieldErrors = data.detail.map(d => {
          const field = d.loc ? d.loc[d.loc.length - 1] : 'Field';
          return `${field}: ${d.msg}`;
        }).join('<br>• ');
        errorMsg += `<br>• ${fieldErrors}`;
      } else if (typeof data.detail === 'string') {
        errorMsg = data.detail;
      }
      showFormError(alertContainer, errorMsg);
      setSubmitLoading(submitBtn, false);
      return;
    }

    showFormError(
      alertContainer,
      data.detail || 'The enquiry service is temporarily unavailable. Your details are preserved. Please retry shortly.'
    );
    setSubmitLoading(submitBtn, false);

  } catch (error) {
    console.error('Enquiry submission error:', error);
    showFormError(
      alertContainer,
      'Unable to connect to the server. Please check your internet connection and retry. Your form inputs have been preserved.'
    );
    setSubmitLoading(submitBtn, false);
  }
}

function getOrCreateAlertContainer(form) {
  let alertBox = form.parentNode.querySelector('.form-alert-container');
  if (!alertBox) {
    alertBox = document.createElement('div');
    alertBox.className = 'form-alert-container hidden mb-4 p-4 rounded-xl text-sm leading-relaxed';
    form.parentNode.insertBefore(alertBox, form);
  }
  return alertBox;
}

function showFormError(container, message) {
  container.className = 'form-alert-container mb-4 p-4 rounded-xl text-sm leading-relaxed bg-red-50 text-red-900 border border-red-200 flex items-start gap-2.5';
  container.innerHTML = `
    <span class="material-symbols-outlined text-[20px] text-red-600 shrink-0 mt-0.5">error</span>
    <div>${message}</div>
  `;
  container.classList.remove('hidden');
  container.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showFormConflict(container, message) {
  container.className = 'form-alert-container mb-4 p-4 rounded-xl text-sm leading-relaxed bg-amber-50 text-amber-900 border border-amber-200 flex items-start gap-2.5';
  container.innerHTML = `
    <span class="material-symbols-outlined text-[20px] text-amber-600 shrink-0 mt-0.5">warning</span>
    <div>
      <strong class="font-semibold block mb-0.5">Existing Enquiry Found</strong>
      <span>${message}</span>
    </div>
  `;
  container.classList.remove('hidden');
  container.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function setSubmitLoading(btn, isLoading) {
  if (!btn) return;
  if (isLoading) {
    btn.dataset.originalHtml = btn.innerHTML;
    btn.innerHTML = `
      <span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span>
      <span>Submitting Assistance Request...</span>
    `;
    btn.style.pointerEvents = 'none';
    btn.classList.add('opacity-75');
  } else {
    if (btn.dataset.originalHtml) {
      btn.innerHTML = btn.dataset.originalHtml;
    }
    btn.style.pointerEvents = 'auto';
    btn.classList.remove('opacity-75');
  }
}
