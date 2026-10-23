using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace SteamFlow.WebApi;

public sealed class AvatarComposer
{
    // WPF rendering needs an STA thread, which thread-pool threads are not.
    public Task ComposeAsync(string avatarPath, string framePath, string outputPath)
    {
        var done = new TaskCompletionSource();
        var thread = new Thread(() =>
        {
            try
            {
                Compose(avatarPath, framePath, outputPath);
                done.SetResult();
            }
            catch (Exception ex)
            {
                done.SetException(ex);
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        return done.Task;
    }

    // The frame is stretched over the avatar, matching the Python plugin's composite.
    private static void Compose(string avatarPath, string framePath, string outputPath)
    {
        var avatar = Load(avatarPath);
        var frame = Load(framePath);
        var bounds = new Rect(0, 0, avatar.PixelWidth, avatar.PixelHeight);

        var visual = new DrawingVisual();
        using (var context = visual.RenderOpen())
        {
            context.DrawImage(avatar, bounds);
            context.DrawImage(frame, bounds);
        }

        var target = new RenderTargetBitmap(avatar.PixelWidth, avatar.PixelHeight, 96, 96, PixelFormats.Pbgra32);
        target.Render(visual);

        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(target));
        var temporary = outputPath + ".tmp";
        using (var stream = File.Create(temporary))
        {
            encoder.Save(stream);
        }

        File.Move(temporary, outputPath, overwrite: true);
    }

    private static BitmapImage Load(string path)
    {
        var image = new BitmapImage();
        image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.UriSource = new Uri(path);
        image.EndInit();
        image.Freeze();
        return image;
    }
}
