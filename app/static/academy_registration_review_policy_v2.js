(() => {
  function polishReview(review) {
    if (!review || review.dataset.registrationReviewPolicyV2 === '1') return;

    const sections = [...review.querySelectorAll('.cam-review-section')];
    const safetySection = sections.find(section => section.querySelector('h3')?.textContent?.trim() === 'Safety Contacts');

    if (safetySection) {
      const heading = safetySection.querySelector('h3');
      if (heading) heading.textContent = 'Emergency Contacts';

      const guardianDt = [...safetySection.querySelectorAll('dt')]
        .find(dt => dt.textContent?.trim() === 'Guardian');
      if (guardianDt) {
        guardianDt.nextElementSibling?.remove();
        guardianDt.remove();
      }
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
