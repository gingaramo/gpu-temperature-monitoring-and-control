// Draws a gauge (like an acceleration or preassure gauge) based on value (0, 100), using canvas in page.
function drawGauge(canvasId, value, unitSuffix) {
    var canvas = document.getElementById(canvasId);
    if (canvas.getContext) {
        var ctx = canvas.getContext('2d');
        var centerX = canvas.width / 2;
        var centerY = canvas.height / 2;
        var radius = Math.min(centerX, centerY) - 10;
        var startAngle = -Math.PI / 2;
        var endAngle = startAngle + (value / 100) * (2 * Math.PI);

        // Clear the canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw the gauge background
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
        ctx.strokeStyle = '#ccc';
        ctx.lineWidth = 10;
        ctx.stroke();

        // Draw the gauge value
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        var color;
        if (value <= 55) {
            color = 'green';
        } else if (value <= 70) {
            color = 'yellow';
        } else {
            color = 'red';
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = 10;
        ctx.stroke();

        // Draw the gauge value text
        ctx.font = '20px Arial';
        ctx.fillStyle = '#000';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(value.toFixed(0) + unitSuffix, centerX, centerY);
    }
}
