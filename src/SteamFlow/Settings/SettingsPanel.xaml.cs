using System.Windows;
using System.Windows.Controls;

namespace SteamFlow.Settings;

public partial class SettingsPanel : UserControl
{
    private readonly Action save;

    public SettingsPanel(PluginSettings settings, Action save)
    {
        this.save = save;
        InitializeComponent();
        DataContext = settings;
    }

    private void OnSettingChanged(object sender, RoutedEventArgs e) => save();

    private void OnSectionExpanded(object sender, RoutedEventArgs e)
    {
        foreach (var section in Sections.Children.OfType<Expander>().Where(section => section != sender))
        {
            section.IsExpanded = false;
        }
    }
}
