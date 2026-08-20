(() => {
  function polishReview(review) {
    if (!review || review.dataset.registrationReviewPolicyV2 === '1') return;

    const sections = [...review.querySelectorAll('.cam-review-section')];
    const safetySection = sections.find(section => section.querySelector('h3')?.textContent?.trim() === 'Safety Contacts');
    const parentSection = sections.find(section => section.querySelector('h3')?.textContent?.trim() === 'Parent');

    let pickupAuthorized = 'Yes';
    if (safetySection) {
      const heading = safetySection.querySelector('h3');
      if (heading) heading.textContent = 'Emergency Contacts';

      const guardianDt = [...safetySection.querySelectorAll('dt')]
        .find(dt => dt.textContent?.trim() === 'Guardian');
      if (guardianDt) {
        const guardianDd = guardianDt.nextElementSibling;
        const guardianText = guardianDd?.textContent?.trim() || '—';
        pickupAuthorized = guardianText === '—' ? 'No' : 'Yes';
        guardianDd?.remove();
        guardianDt.remove();
      }
    }

    const parentDl = parentSection?.querySelector('dl');
    if (parentDl && ![...parentDl.querySelectorAll('dt')].some(dt => dt.textContent?.trim() === 'Pickup Authorized')) {
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = 'Pickup Authorized';
      dd.textContent = pickupAuthorized;
      parentDl.append(dt, dd);
    }

    review.dataset.registrationReviewPolicyV2 = '1';
  }

  function apply() {
    document.querySelectorAll('.cam-registration-review').forEach(polishReview);
  }

  document.addEventListener('DOMContentLoaded', apply);
  new MutationObserver(apply).observe(document.documentElement, { childList: true, subtree: true });
  apply();
})();
