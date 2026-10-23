using System.Runtime.InteropServices;
using System.Windows;

namespace SteamFlow;

public static class ClipboardText
{
    // The WPF clipboard only works on an STA thread, and Flow does not promise which thread runs an action.
    public static Task<string> ReadAsync()
    {
        var result = new TaskCompletionSource<string>();
        var thread = new Thread(() =>
        {
            try
            {
                result.SetResult(Clipboard.ContainsText() ? Clipboard.GetText() : "");
            }
            catch (Exception ex) when (ex is COMException or ExternalException)
            {
                result.SetResult("");
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        return result.Task;
    }
}
