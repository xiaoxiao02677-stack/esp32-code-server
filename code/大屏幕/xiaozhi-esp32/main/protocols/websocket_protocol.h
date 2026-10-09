#ifndef _WEBSOCKET_PROTOCOL_H_
#define _WEBSOCKET_PROTOCOL_H_


#include "protocol.h"

#include <web_socket.h>
#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>

#define WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT (1 << 0)

class WebsocketProtocol : public Protocol {
public:
    WebsocketProtocol();
    ~WebsocketProtocol();

    bool Start() override;
    bool SendAudio(std::unique_ptr<AudioStreamPacket> packet) override;
    bool OpenAudioChannel() override;
    void CloseAudioChannel(bool send_goodbye = true) override;
    bool IsAudioChannelOpened() const override;

private:
    EventGroupHandle_t event_group_handle_;
    std::unique_ptr<WebSocket> websocket_;
    int version_ = 1;
    bool send_audio_error_state_ = false;
    uint32_t send_audio_drop_count_ = 0;
    bool binary_frame_error_state_ = false;
    uint32_t binary_frame_drop_count_ = 0;

    void ParseServerHello(const cJSON* root);
    void ReportBinaryFrameError(size_t len, size_t payload_size);
    void ReportBinaryFrameRecovered();
    bool SendText(const std::string& text) override;
    std::string GetHelloMessage();
};

#endif
