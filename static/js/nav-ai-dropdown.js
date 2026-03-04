(function () {
    const navContainer = document.querySelector('.nav-container');
    const navBrand = navContainer ? navContainer.querySelector('.nav-brand-wrap') : null;
    const navTagline = navContainer ? navContainer.querySelector('.nav-tagline-wrap') : null;
    const navRight = navContainer ? navContainer.querySelector('.nav-right') : null;
    const navLexikon = navContainer ? navContainer.querySelector('.nav-moment-link--lexikon') : null;
    const navModelDropdown = navTagline ? navTagline.querySelector('[data-ai-dropdown]') : null;
    const navModelTrigger = navTagline ? navTagline.querySelector('.nav-ai-trigger') : null;
    const navTaglineText = navTagline ? navTagline.querySelector('.nav-tagline') : null;

    const getLexikonNaturalWidth = () => {
        if (!navLexikon) {
            return 0;
        }
        const measured = navLexikon.getBoundingClientRect().width;
        if (measured > 0) {
            navLexikon.dataset.fullWidth = measured.toFixed(2);
            return measured;
        }
        const stored = Number.parseFloat(navLexikon.dataset.fullWidth || '0');
        return Number.isFinite(stored) ? stored : 0;
    };

    const getModelNaturalWidth = () => {
        if (!navModelTrigger) {
            return 0;
        }
        const measured = navModelTrigger.getBoundingClientRect().width;
        if (measured > 0) {
            navModelTrigger.dataset.fullWidth = measured.toFixed(2);
            return measured;
        }
        const stored = Number.parseFloat(navModelTrigger.dataset.fullWidth || '0');
        return Number.isFinite(stored) ? stored : 0;
    };

    const getTaglineNaturalWidth = () => {
        if (!navTaglineText) {
            return 0;
        }
        const measured = navTaglineText.getBoundingClientRect().width;
        const scrolled = navTaglineText.scrollWidth || 0;
        const width = Math.max(measured, scrolled);
        if (width > 0) {
            navTaglineText.dataset.fullWidth = width.toFixed(2);
            return width;
        }
        const stored = Number.parseFloat(navTaglineText.dataset.fullWidth || '0');
        return Number.isFinite(stored) ? stored : 0;
    };

    const closeModelDropdown = () => {
        if (!navModelDropdown) {
            return;
        }
        navModelDropdown.classList.remove('is-open');
        const trigger = navModelDropdown.querySelector('.nav-ai-trigger');
        if (trigger) {
            trigger.setAttribute('aria-expanded', 'false');
        }
    };

    const syncLexikonVisibility = () => {
        if (!navContainer || !navBrand || !navTagline || !navRight) {
            return;
        }

        if (window.getComputedStyle(navTagline).display === 'none') {
            if (navLexikon) {
                navLexikon.classList.remove('is-auto-hidden');
            }
            if (navModelDropdown) {
                navModelDropdown.classList.remove('is-auto-hidden');
            }
            return;
        }

        const navStyles = window.getComputedStyle(navContainer);
        const gapValue = Number.parseFloat(navStyles.columnGap || '0');
        const columnGap = Number.isFinite(gapValue) ? gapValue : 0;
        const paddingLeft = Number.parseFloat(navStyles.paddingLeft || '0');
        const paddingRight = Number.parseFloat(navStyles.paddingRight || '0');
        const containerInnerWidth = Math.max(0, navContainer.clientWidth - paddingLeft - paddingRight);
        const nonTaglineWidth = navBrand.scrollWidth + navRight.scrollWidth + (columnGap * 2);
        const availableForTagline = containerInnerWidth - nonTaglineWidth;

        if (navLexikon) {
            const lexikonNaturalWidth = getLexikonNaturalWidth();
            const modelWidth = getModelNaturalWidth();
            const remainingSpaceWithLexikon = availableForTagline + (navLexikon.classList.contains('is-auto-hidden') ? lexikonNaturalWidth : 0);

            if (remainingSpaceWithLexikon < modelWidth) {
                navLexikon.classList.add('is-auto-hidden');
            } else {
                navLexikon.classList.remove('is-auto-hidden');
            }
        }

        if (!navModelDropdown) {
            return;
        }

        const taglineNaturalWidth = getTaglineNaturalWidth();
        const modelWidth = navModelTrigger ? navModelTrigger.getBoundingClientRect().width : 0;
        const modelNaturalWidth = Math.max(modelWidth, getModelNaturalWidth());
        const gapBetweenTaglineAndModel = 12;
        const requiredWidthWithModel = taglineNaturalWidth + modelNaturalWidth + gapBetweenTaglineAndModel;
        const requiredWidthWithoutModel = taglineNaturalWidth;
        const revealThreshold = 18;

        if (availableForTagline < requiredWidthWithModel) {
            closeModelDropdown();
            navModelDropdown.classList.add('is-auto-hidden');
        } else {
            const canShowAgain = availableForTagline >= (requiredWidthWithoutModel + modelNaturalWidth + revealThreshold);
            if (canShowAgain) {
                navModelDropdown.classList.remove('is-auto-hidden');
            }
        }
    };

    let navResizeRaf = null;
    const scheduleLexikonSync = () => {
        if (navResizeRaf !== null) {
            window.cancelAnimationFrame(navResizeRaf);
        }
        navResizeRaf = window.requestAnimationFrame(() => {
            navResizeRaf = null;
            syncLexikonVisibility();
        });
    };

    if (navContainer && (navLexikon || navModelDropdown)) {
        scheduleLexikonSync();
        window.addEventListener('load', scheduleLexikonSync);
        window.addEventListener('resize', scheduleLexikonSync);
        if ('ResizeObserver' in window) {
            const navResizeObserver = new window.ResizeObserver(scheduleLexikonSync);
            [navContainer, navBrand, navTagline, navTaglineText, navRight, navModelTrigger, navModelDropdown].forEach((node) => {
                if (node) {
                    navResizeObserver.observe(node);
                }
            });
        }
    }

    const dropdowns = Array.from(document.querySelectorAll('[data-ai-dropdown]'));
    if (!dropdowns.length) {
        return;
    }

    const getCookie = (name) => {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift() || '';
        }
        return '';
    };

    const closeDropdown = (dropdown) => {
        dropdown.classList.remove('is-open');
        const trigger = dropdown.querySelector('.nav-ai-trigger');
        if (trigger) {
            trigger.setAttribute('aria-expanded', 'false');
        }
    };

    const closeAll = () => {
        dropdowns.forEach((dropdown) => closeDropdown(dropdown));
    };

    dropdowns.forEach((dropdown) => {
        const trigger = dropdown.querySelector('.nav-ai-trigger');
        if (!trigger) {
            return;
        }

        trigger.addEventListener('click', (event) => {
            event.preventDefault();
            const shouldOpen = !dropdown.classList.contains('is-open');
            closeAll();
            if (shouldOpen) {
                dropdown.classList.add('is-open');
                trigger.setAttribute('aria-expanded', 'true');
            }
        });

        const switchUrl = dropdown.dataset.aiSwitchUrl;
        const options = Array.from(dropdown.querySelectorAll('[data-ai-model-option]'));
        const activeLabel = dropdown.querySelector('.nav-ai-dropdown-active');
        const triggerLabel = dropdown.querySelector('.nav-ai-trigger-model');
        const statusEl = dropdown.querySelector('[data-ai-switch-status]');
        if (!switchUrl || !options.length) {
            return;
        }

        const setStatus = (text, isError) => {
            if (!statusEl) {
                return;
            }
            statusEl.textContent = text || '';
            statusEl.classList.toggle('is-error', Boolean(isError));
        };

        options.forEach((option) => {
            option.addEventListener('click', async (event) => {
                event.preventDefault();
                if (dropdown.classList.contains('is-switching')) {
                    return;
                }
                const modelRef = (option.dataset.modelRef || '').trim();
                if (!modelRef) {
                    return;
                }

                const oldLabel = triggerLabel ? triggerLabel.textContent : '';
                dropdown.classList.add('is-switching');
                setStatus('Prepínam model, prosím počkaj…', false);
                if (triggerLabel) {
                    triggerLabel.textContent = 'Prepínam model…';
                }
                if (activeLabel) {
                    activeLabel.textContent = 'Prepínam model…';
                }

                try {
                    const response = await fetch(switchUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken'),
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body: JSON.stringify({ model_ref: modelRef }),
                    });
                    const payload = await response.json().catch(() => ({}));
                    if (!response.ok) {
                        const err = payload.error || 'Prepnutie modelu zlyhalo.';
                        throw new Error(err);
                    }
                    setStatus('Model úspešne prepnutý. Obnovujem stránku…', false);
                    window.location.reload();
                } catch (err) {
                    const msg = (err && err.message) ? err.message : 'Prepnutie modelu zlyhalo.';
                    setStatus(msg, true);
                    if (triggerLabel) {
                        triggerLabel.textContent = oldLabel;
                    }
                    if (activeLabel) {
                        activeLabel.textContent = oldLabel;
                    }
                    dropdown.classList.remove('is-switching');
                }
            });
        });
    });

    document.addEventListener('click', (event) => {
        const clickedInside = dropdowns.some((dropdown) => dropdown.contains(event.target));
        if (!clickedInside) {
            closeAll();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeAll();
        }
    });
})();
