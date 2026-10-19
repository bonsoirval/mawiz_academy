/* Admin resource modals. Kept in an external file to comply with the app's
   Content-Security-Policy (script-src 'self'), which blocks inline scripts. */
(() => {
  'use strict';

  function getDialog(id) {
    if (!id) return null;
    return document.getElementById(id);
  }

  function openDialog(id) {
    const dialog = getDialog(id);
    if (!dialog || !dialog.matches('dialog')) {
      console.error('Manage dialog not found:', id);
      return;
    }
    // Dialogs emitted inside table rows are invalid HTML; relocate them before opening.
    if (dialog.closest('table')) document.body.appendChild(dialog);
    try {
      if (typeof dialog.showModal === 'function') {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute('open', '');
        dialog.classList.add('manage-dialog-fallback-open');
      }
    } catch (error) {
      // Fallback for browsers with partial dialog support.
      dialog.setAttribute('open', '');
      dialog.classList.add('manage-dialog-fallback-open');
    }
  }

  function closeDialog(id) {
    const dialog = getDialog(id);
    if (!dialog) return;
    try {
      if (typeof dialog.close === 'function' && dialog.open) dialog.close();
    } catch (_) { /* continue with the fallback cleanup */ }
    dialog.removeAttribute('open');
    dialog.classList.remove('manage-dialog-fallback-open');
  }

  function normalizeDialogs() {
    document.querySelectorAll('dialog.manage-dialog').forEach((dialog) => {
      if (dialog.closest('table')) document.body.appendChild(dialog);
      if (dialog.dataset.manageBound === 'true') return;
      dialog.dataset.manageBound = 'true';
      dialog.addEventListener('click', (event) => {
        if (event.target === dialog) closeDialog(dialog.id);
      });
    });
  }

  // Project form selectors are cascading: a lesson implies its module/course,
  // and a module implies its course. This works for both create and edit forms.
  function setupProjectForm(form) {
    const track = form.querySelector('[data-project-track]');
    const course = form.querySelector('[data-project-course]');
    const module = form.querySelector('[data-project-module]');
    const lesson = form.querySelector('[data-project-lesson]');
    if (!course || !module || !lesson) return;

    const toggleOptions = (select, predicate) => {
      Array.from(select.options).forEach((option, index) => {
        if (index === 0) { option.hidden = false; option.disabled = false; return; }
        const allowed = predicate(option);
        option.hidden = !allowed;
        option.disabled = !allowed;
        if (!allowed && option.selected) select.value = '0';
      });
    };

    const updateCourses = () => {
      if (track && track.value !== '0') {
        const tid = track.value;
        toggleOptions(course, option => (option.dataset.trackIds || '').split(',').includes(tid));
      } else {
        toggleOptions(course, () => true);
      }
      updateModules();
    };
    const updateModules = () => {
      const cid = course.value;
      toggleOptions(module, option => cid !== '0' && option.dataset.courseId === cid);
      updateLessons();
    };
    const updateLessons = () => {
      const mid = module.value;
      toggleOptions(lesson, option => mid !== '0' && option.dataset.moduleId === mid);
    };

    if (track) track.addEventListener('change', () => {
      // Track changes invalidate a course if it is no longer in that track.
      updateCourses();
    });
    course.addEventListener('change', updateModules);
    module.addEventListener('change', () => {
      const selected = module.options[module.selectedIndex];
      if (selected && selected.dataset.courseId && selected.value !== '0') {
        course.value = selected.dataset.courseId;
        if (track) {
          const courseOption = course.options[course.selectedIndex];
          const trackIds = (courseOption?.dataset.trackIds || '').split(',').filter(Boolean);
          if (trackIds.length && !trackIds.includes(track.value)) track.value = trackIds[0];
        }
        updateCourses();
        module.value = selected.value;
      }
      updateLessons();
    });
    lesson.addEventListener('change', () => {
      const selected = lesson.options[lesson.selectedIndex];
      if (selected && selected.dataset.moduleId && selected.value !== '0') {
        module.value = selected.dataset.moduleId;
        const moduleOption = module.options[module.selectedIndex];
        if (moduleOption?.dataset.courseId) course.value = moduleOption.dataset.courseId;
        updateCourses();
        module.value = selected.dataset.moduleId;
        updateLessons();
        lesson.value = selected.value;
      }
    });
    updateCourses();
  }

  document.addEventListener('click', (event) => {
    const openButton = event.target.closest('[data-manage-open]');
    if (openButton) {
      event.preventDefault();
      openDialog(openButton.dataset.manageOpen);
      return;
    }
    const closeButton = event.target.closest('[data-manage-close]');
    if (closeButton) {
      event.preventDefault();
      closeDialog(closeButton.dataset.manageClose);
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      normalizeDialogs();
      document.querySelectorAll('form.project-form').forEach(setupProjectForm);
    }, { once: true });
  } else {
    normalizeDialogs();
    document.querySelectorAll('form.project-form').forEach(setupProjectForm);
  }
})();
