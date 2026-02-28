/**
 * Lock-free SPSC (Single-Producer Single-Consumer) ring buffer.
 *
 * Producer: hook callback thread (DLL)
 * Consumer: C# InputMonitor polling thread
 *
 * Uses atomic operations for thread-safe, lock-free access.
 * Power-of-two capacity for fast modulo via bitmask.
 */

#ifndef RINGBUFFER_H
#define RINGBUFFER_H

#include <windows.h>
#include <stdint.h>

/* Event type discriminator. */
typedef enum {
    HOOK_EVENT_KEYBOARD = 1,
    HOOK_EVENT_MOUSE = 2,
} HookEventType;

/* Keyboard event data from WH_KEYBOARD_LL. */
typedef struct {
    uint32_t vkCode;
    uint32_t scanCode;
    uint32_t flags;
    uint32_t action;  /* WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP */
} KeyboardEventData;

/* Mouse event data from WH_MOUSE_LL. */
typedef struct {
    int32_t x;
    int32_t y;
    uint32_t mouseData;
    uint32_t action;  /* WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MOUSEMOVE, etc. */
} MouseEventData;

/* Union event structure written to the ring buffer. */
typedef struct {
    HookEventType type;
    uint32_t timestamp_ms;  /* From KBDLLHOOKSTRUCT.time or MSLLHOOKSTRUCT.time */
    union {
        KeyboardEventData keyboard;
        MouseEventData mouse;
    };
} HookEvent;

/* Ring buffer state. */
typedef struct {
    HookEvent* buffer;
    uint32_t capacity;   /* Must be power of two. */
    uint32_t mask;       /* capacity - 1, for fast modulo. */
    volatile LONG head;  /* Write position (producer). */
    volatile LONG tail;  /* Read position (consumer). */
} RingBuffer;

/**
 * Initialize the ring buffer. Rounds capacity up to the next power of two.
 * @return TRUE on success.
 */
static inline BOOL RingBuffer_Init(RingBuffer* rb, uint32_t requestedCapacity)
{
    /* Round up to next power of two. */
    uint32_t capacity = 1;
    while (capacity < requestedCapacity)
        capacity <<= 1;

    rb->buffer = (HookEvent*)HeapAlloc(
        GetProcessHeap(), HEAP_ZERO_MEMORY, capacity * sizeof(HookEvent));
    if (!rb->buffer)
        return FALSE;

    rb->capacity = capacity;
    rb->mask = capacity - 1;
    rb->head = 0;
    rb->tail = 0;
    return TRUE;
}

/** Free ring buffer memory. */
static inline void RingBuffer_Destroy(RingBuffer* rb)
{
    if (rb->buffer)
    {
        HeapFree(GetProcessHeap(), 0, rb->buffer);
        rb->buffer = NULL;
    }
}

/**
 * Write a single event (producer side — hook callback).
 * If the buffer is full, the oldest unread event is silently dropped.
 */
static inline void RingBuffer_Write(RingBuffer* rb, const HookEvent* evt)
{
    LONG head = InterlockedCompareExchange(&rb->head, 0, 0);
    LONG nextHead = (head + 1) & rb->mask;

    /* If buffer is full, advance tail (drop oldest). */
    LONG tail = InterlockedCompareExchange(&rb->tail, 0, 0);
    if (nextHead == tail)
    {
        InterlockedCompareExchange(&rb->tail, (tail + 1) & rb->mask, tail);
    }

    rb->buffer[head & rb->mask] = *evt;
    MemoryBarrier();
    InterlockedExchange(&rb->head, nextHead);
}

/**
 * Read a batch of events (consumer side — C# polling thread).
 * @return Number of events read.
 */
static inline uint32_t RingBuffer_ReadBatch(
    RingBuffer* rb, HookEvent* outEvents, uint32_t maxEvents)
{
    uint32_t count = 0;
    LONG tail = InterlockedCompareExchange(&rb->tail, 0, 0);
    LONG head = InterlockedCompareExchange(&rb->head, 0, 0);

    while (tail != head && count < maxEvents)
    {
        outEvents[count] = rb->buffer[tail & rb->mask];
        count++;
        tail = (tail + 1) & rb->mask;
    }

    if (count > 0)
    {
        MemoryBarrier();
        InterlockedExchange(&rb->tail, tail);
    }

    return count;
}

#endif /* RINGBUFFER_H */
