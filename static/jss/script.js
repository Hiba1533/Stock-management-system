$(document).ready(function () {
    // Enhanced Sidebar Toggle with Animation
    $('#sidebarCollapse').on('click', function () {
        $('#sidebar').toggleClass('active');
        $(this).toggleClass('collapsed');
    });

    // Modern Tooltips with Delay
    $('[data-bs-toggle="tooltip"]').tooltip({
        delay: { "show": 300, "hide": 100 },
        trigger: 'hover focus'
    });

    // Improved Active Menu Detection
    const currentUrl = window.location.pathname;
    $('#sidebar a').each(function() {
        const $this = $(this);
        if ($this.attr('href') === currentUrl || 
            currentUrl.startsWith($this.attr('href'))) {
            $this.addClass('active');
            $this.closest('.collapse').addClass('show');
            
            // Highlight parent menu items
            $this.parentsUntil('#sidebar', 'li').addClass('menu-open');
        }
    });

    // Enhanced Table Interactions
    $('table tr').click(function() {
        $(this).toggleClass('table-active').siblings().removeClass('table-active');
    }).hover(function() {
        $(this).css('cursor', 'pointer');
    });

    // Advanced Form Validation
    $('form').submit(function(e) {
        let valid = true;
        $(this).find('[required]').each(function() {
            const $field = $(this);
            if (!$field.val()) {
                $field.addClass('is-invalid');
                $field.next('.invalid-feedback').remove();
                $field.after('<div class="invalid-feedback">This field is required</div>');
                valid = false;
            } else {
                $field.removeClass('is-invalid');
                $field.next('.invalid-feedback').remove();
            }
        });
        
        if (!valid) {
            e.preventDefault();
            $('html, body').animate({
                scrollTop: $('.is-invalid').first().offset().top - 100
            }, 300);
        }
        return valid;
    });

    // Add Modern Card Animations
    $('.card').each(function(index) {
        $(this).css({
            'opacity': '0',
            'transform': 'translateY(20px)',
            'transition': 'all 0.4s ease-out',
            'transition-delay': (index * 0.05) + 's'
        }).delay(index * 50).queue(function() {
            $(this).css({
                'opacity': '1',
                'transform': 'translateY(0)'
            }).dequeue();
        });
    });

    // Responsive Adjustments
    function handleResponsive() {
        if ($(window).width() < 992) {
            $('#sidebar').removeClass('active');
        } else {
            $('#sidebar').addClass('active');
        }
    }

    $(window).on('resize', handleResponsive);
    handleResponsive();
});