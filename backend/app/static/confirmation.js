/**
 * MB Associates Solar Website — Confirmation Page Script
 * Reads the validated reference code and enquiry details from sessionStorage.
 * Populates real tracking reference and avoids exposing customer data in URLs.
 * If no enquiry session is found, redirects to the enquiry form.
 */

document.addEventListener('DOMContentLoaded', function () {
  try {
    const rawData = sessionStorage.getItem('mb_enquiry');
    if (!rawData) {
      console.warn('No active enquiry session found in sessionStorage. Redirecting to /enquiry...');
      window.location.href = '/enquiry';
      return;
    }

    const enquiry = JSON.parse(rawData);
    if (!enquiry || !enquiry.reference) {
      console.warn('Invalid enquiry session. Redirecting to /enquiry...');
      window.location.href = '/enquiry';
      return;
    }

    // 1. Update Reference Code Elements
    const refElements = document.querySelectorAll('#reference-code, [data-reference-target]');
    refElements.forEach(el => {
      el.textContent = enquiry.reference;
    });

    // 2. Format and display submitted timestamp
    const timestampEl = document.getElementById('live-timestamp');
    if (timestampEl) {
      try {
        const dateObj = enquiry.created_at ? new Date(enquiry.created_at) : new Date();
        const formatted = dateObj.toLocaleDateString('en-IN', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          timeZoneName: 'short'
        });
        timestampEl.textContent = formatted;
      } catch (err) {
        console.error('Timestamp format error:', err);
      }
    }

    // 3. Update summary parameters if available on confirmation page
    const summaryPills = document.querySelectorAll('.grid.grid-cols-1.sm\\:grid-cols-2 .p-space-md');
    if (summaryPills.length >= 4) {
      // Preferred Contact Channel
      if (enquiry.contact_method) {
        const methodVal = summaryPills[0].querySelector('.font-title-md');
        if (methodVal) {
          methodVal.textContent = enquiry.contact_method.toUpperCase() + ' (' + (enquiry.contact_detail || 'Registered') + ')';
        }
      }

      // Property & Roof Category
      if (enquiry.property_type) {
        const propVal = summaryPills[1].querySelector('.font-title-md');
        if (propVal) {
          propVal.textContent = enquiry.property_type;
        }
      }

      // Help Scope Requested
      if (enquiry.assistance && enquiry.assistance.length > 0) {
        const helpVal = summaryPills[2].querySelector('.font-title-md');
        if (helpVal) {
          helpVal.textContent = enquiry.assistance.slice(0, 2).join(', ') + 
            (enquiry.assistance.length > 2 ? ` (+${enquiry.assistance.length - 2} more)` : '');
        }
      }

      // PIN Code Location
      if (enquiry.pin_code) {
        const pinVal = summaryPills[3].querySelector('.font-title-md');
        if (pinVal) {
          pinVal.textContent = 'PIN Code ' + enquiry.pin_code;
        }
      }
    }

  } catch (e) {
    console.error('Error populating enquiry confirmation details:', e);
  }
});
