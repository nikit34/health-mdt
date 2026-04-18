# Apple Reminders интеграция

Для закрытия цикла «GP предложил задачу → она попала в твой планировщик» в Consilium
используется iOS Shortcut. Один раз поставь — дальше любая задача ⏰ из веба/бота
создаёт напоминание в приложении Reminders.

## Установка шортката (iOS/macOS)

1. Открой приложение **Shortcuts (Команды)**.
2. Создай новый шорткат с именем **Consilium Add**.
3. Добавь действия:
   - **Get Input from Shortcut** — тип Text.
   - **Split Text** — разделитель: `||`
   - **Get Item from List** — Item 1 (title)
   - **Get Item from List** — Item 2 (notes)
   - **Get Item from List** — Item 3 (due date, ISO)
   - **Add New Reminder**:
     - Title: Item 1
     - Notes: Item 2
     - Due: Item 3 (если пусто — без даты)
     - List: выбери «Health» или любой другой
4. В настройках шортката включи **Show in Share Sheet** и **Allow Untrusted Shortcuts**.

## Как это работает

Каждая задача в Consilium имеет поле `reminders_url` вида:

```
shortcuts://run-shortcut?name=Consilium%20Add&input=Title||Detail||2026-04-22
```

На iPhone тап по этой ссылке из бота / Safari / веб-интерфейса запустит шорткат
и создаст reminder без дополнительных действий.

## Альтернатива: macOS URL scheme

Если ты на Mac — iCloud синхронизирует список, и задача сразу появится в Reminders.app
на всех устройствах.
