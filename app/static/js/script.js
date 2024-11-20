const socket = io();

socket.on('update_events', function(data) {
    // Atualiza a interface com as informações de eventos
    console.log(data);
});

function reserveEvent(eventId) {
    socket.emit('reserve_event', { eventId: eventId });
}